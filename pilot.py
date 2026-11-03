"""Single-process, localhost-only persistent avatar experiment."""
from avatar_setup import register_setup
from benchmark_report import register_benchmark_report
import base64
import io
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, abort, jsonify, render_template, request, send_file, session
from PIL import Image, ImageOps, UnidentifiedImageError
from avatar_pipeline import (MODES, POSE, RENDERER_VERSION, base_prompt, cache_key,
                             edit_mask, edit_prompt, outfit_spec, preserve_head, valid_box)
from pilot_store import PilotStore
from fashn import FashnJobs
from weather_live import register_weather, CATALOG, outfit, signature
from weather_radar import register_radar
from wardrobe_photos import register_garments
from avatar_pipeline import clothing_edit_mask, compose_clothes

MODEL = 'gpt-image-1.5'
PRICING_DATE = '2026-10-29'
OUTPUT_PRICES = {'low': .013, 'medium': .05, 'high': .20}
SCENARIOS = {
    'sun': ('Warm & sunny', '28°C · light breeze', 'An ivory breathable linen short-sleeve shirt, tailored olive linen trousers, white low-top sneakers, no accessories covering the face.'),
    'rain': ('Rainy commute', '12°C · rain · wind', 'A fitted olive waterproof zip jacket without a hood, charcoal trousers and waterproof dark low-profile shoes.'),
    'cold': ('Cold morning', '2°C · chilly wind', 'A fitted charcoal insulated hip-length jacket over a cream knit sweater, wool trousers, dark insulated boots and gloves, no scarf. Face unobstructed.'),
}


def normalize_photo(raw):
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError('Choose a JPEG, PNG or WebP under 8 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > 25_000_000:
                raise ValueError('Use a JPEG, PNG or WebP under 25 megapixels.')
            if min(source.size) < 256:
                raise ValueError('Use a photo at least 256 pixels on each side.')
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1536, 1536))
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=92)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('This image could not be read. Try a JPEG, PNG or WebP.') from exc


def estimated_cost(usage):
    """Undiscounted standard token rates; unknown usage stays unknown, never zero."""
    details = usage.get('input_tokens_details', {})
    values = [details.get('text_tokens'), details.get('image_tokens'), usage.get('output_tokens')]
    if any(not isinstance(v, (int, float)) or v < 0 for v in values):
        return None
    return round((values[0] * 5 + values[1] * 8 + values[2] * 32) / 1_000_000, 6)


def generate(photo, scenario, quality, *, mode='selfie', preferences='', head_box=None, clothing_regions=None):
    prompt = base_prompt(preferences) if mode == 'base' else edit_prompt(SCENARIOS[scenario][2], mode)
    with Image.open(io.BytesIO(photo)) as image:
        output = io.BytesIO()
        image.convert('RGB').save(output, format='PNG')
        reference = output.getvalue()
    files = {'image': ('reference.png', reference, 'image/png')}
    if mode == 'protected':
        files['mask'] = ('mask.png', edit_mask(reference, head_box), 'image/png')
    if mode == 'clothes':
        files['mask'] = ('clothing-mask.png', clothing_edit_mask(reference, clothing_regions), 'image/png')
        prompt += ' Change only the clothing inside the transparent mask. The mask includes a narrow background margin to allow natural garment edges; keep that surrounding background visually identical. Render complete, smoothly contoured sleeves and shoulders, never a cutout or a polygon-shaped edge. Never change exposed skin, hands, head, pose, body scale, background or feet placement. Fit new garments to the existing body. No shorts, no exposed legs, no hoods, no new accessories.'
    response = requests.post('https://api.openai.com/v1/images/edits',
        headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']}, files=files,
        data={'model': MODEL, 'prompt': prompt, 'quality': quality,
              'size': '1024x1536', 'input_fidelity': 'high', 'n': '1', 'output_format': 'png'},
        timeout=(10, 240))
    if response.status_code != 200:
        messages = {400: 'OpenAI rejected this request or image.', 401: 'The OpenAI credential was rejected.',
                    403: 'Image model access requires permission or organization verification.',
                    429: 'OpenAI quota or rate limit reached.'}
        raise RuntimeError(messages.get(response.status_code, 'OpenAI could not complete this image.') + ' No automatic retry was made.')
    result = response.json()
    return base64.b64decode(result['data'][0]['b64_json'], validate=True), result.get('usage', {})


def create_app(renderer=generate, store_path=None, fashn_client=None, fashn_autostart=True):
    app = Flask(__name__)
    store = PilotStore(store_path or os.path.join(app.instance_path, 'avatar-pilot', 'pilot.sqlite3'))
    app.secret_key = store.setting('secret')
    app.config.update(MAX_CONTENT_LENGTH=9 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_NAME='weatheravatar_pilot', TRUSTED_HOSTS=['127.0.0.1', 'localhost'])
    state = store.load()
    lock = threading.RLock()
    pool = ThreadPoolExecutor(max_workers=1)
    submitted = store.count()
    app.extensions['pilot_state'] = state
    app.extensions['pilot_store'] = store
    app.extensions['pilot_pool'] = pool
    fashn = FashnJobs(store.db, lock, client=fashn_client, autostart=False, user_limit=int(os.environ.get('FASHN_USER_CREDIT_LIMIT', '12')), global_limit=int(os.environ.get('FASHN_GLOBAL_CREDIT_LIMIT', '24')))
    app.extensions['fashn'] = fashn
    weather_profile = register_weather(app, store, lock)
    register_radar(app, weather_profile)
    register_garments(app, store, lock, fashn, weather_profile)
    register_setup(app, store, lock, fashn, weather_profile)
    register_benchmark_report(app,fashn)

    @app.before_request
    def protect():
        if request.remote_addr not in {'127.0.0.1', '::1'}:
            abort(403)
        if 'owner' not in session:
            session.permanent = True
            session['owner'] = secrets.token_hex(24)
            session['csrf'] = secrets.token_hex(24)
        if request.method != 'GET' and not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
            abort(403)

    @app.after_request
    def private(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error='Choose an image under 8 MB.'), 413

    def owned():
        value = state.get(session['owner'])
        if value is None:
            abort(404)
        return value

    def public(job):
        return {k: v for k, v in job.items() if k != 'image'}

    @app.get('/')
    @app.get('/pilot')
    def index():
        return render_template('wardrobe.html', csrf=session['csrf'])

    @app.get('/evaluate')
    def evaluate():
        return render_template('pilot.html', csrf=session['csrf'])

    @app.get('/api/pilot')
    def status():
        with lock:
            record = state.get(session['owner'], {})
            return jsonify(ready=bool(os.environ.get('OPENAI_API_KEY')), photo=bool(record.get('photo')),
                           jobs=[public(j) for j in record.get('jobs', [])], remaining=max(0, 24-submitted), model=MODEL,
                           avatars=record.get('avatars', []), active_avatar=record.get('active_avatar'), permanent_avatar=record.get('permanent_avatar'),
                           outfits={k: outfit_spec(k) for k in SCENARIOS})

    @app.get('/api/fashn')
    def fashn_status():
        owner = session['owner']
        fashn.kick()
        with lock:
            return jsonify(ready=fashn.client.ready, photo=bool(state.get(owner, {}).get('photo')),
                           jobs=fashn.public_jobs(owner), avatar=fashn.approved(owner),
                           profile=weather_profile(owner), catalog=CATALOG,
                           weather_matches=app.extensions['weather_matches'](owner),
                           weather_pending=app.extensions['weather_matches'](owner,True),
                           user_credit_limit=fashn.user_limit, global_credit_limit=fashn.global_limit,
                           outfits={k: {'items': [{'id': SCENARIOS[k][2]}]} for k in SCENARIOS})

    @app.post('/api/fashn/base')
    @app.post('/api/fashn/dress')
    def fashn_generate():
        body = request_body()
        if body.get('consent') is not True:
            return jsonify(error='Confirm sending your saved image to FASHN.'), 400
        owner = session['owner']
        kind = 'base' if request.path.endswith('/base') else 'outfit'
        scenario = body.get('scenario', '')
        if kind == 'outfit' and (not isinstance(scenario, str) or scenario not in CATALOG):
            return jsonify(error='Choose a weather preview.'), 400
        if kind == 'outfit' and weather_profile(owner).get('weather_outfits'):
            try:job,reused=app.extensions['enqueue_weather_outfit'](owner,scenario)
            except ValueError as exc:return jsonify(error=str(exc)),409
            return jsonify(id=job,reused=reused),200 if reused else 202
        with lock:
            avatar = fashn.approved(owner) if kind == 'outfit' else None
            if kind == 'base':
                rejected = [j for j in fashn.public_jobs(owner) if j.get('kind')=='base' and j.get('rejected')]
                base_revision = len(rejected) or None
            source = fashn.image(owner, avatar) if avatar else state.get(owner, {}).get('photo')
            if not source or (kind == 'outfit' and not avatar):
                return jsonify(error='Upload a photo and approve a FASHN base avatar first.'), 400
            try:
                job, reused = fashn.enqueue(owner, source, kind, scenario, avatar if kind=='outfit' else base_revision,
                                           outfit(weather_profile(owner),scenario) if kind=='outfit' else '',
                                           signature(weather_profile(owner),scenario) if kind=='outfit' else None)
            except ValueError as exc:
                return jsonify(error=str(exc)), 409
        return jsonify(id=job, reused=reused), 200 if reused else 202

    @app.post('/api/fashn/photo-preview')
    def photo_preview():
        if request.form.get('consent') != 'true':
            return jsonify(error='Confirm sending this photo to FASHN to create a preview.'), 400
        file = request.files.get('photo')
        try:
            photo = normalize_photo(file.read() if file else b'')
            with lock:
                job, reused = fashn.enqueue(session['owner'], photo, 'base')
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        # Separate candidate: never replace the saved reference or approved avatar.
        return jsonify(id=job, reused=reused), 200 if reused else 202

    @app.post('/api/fashn/reject')
    def fashn_reject():
        import json
        body=request_body(); owner=session['owner']
        with lock, store.db:
            row=store.db.execute("SELECT metadata FROM fashn_jobs WHERE owner=? AND id=? AND status='done' AND deleted=0",(owner,body.get('job_id'))).fetchone()
            if not row or fashn.approved(owner)==body.get('job_id'):return jsonify(error='Choose an unapproved candidate'),400
            m=json.loads(row[0])
            if m.get('kind')!='base':return jsonify(error='Choose a base avatar'),400
            m['rejected']=True
            store.db.execute('UPDATE fashn_jobs SET metadata=? WHERE id=?',(json.dumps(m),body['job_id']))
        return jsonify(ok=True)

    @app.post('/api/fashn/approve')
    def fashn_approve():
        body = request_body()
        if body.get('approved') is not True or not isinstance(body.get('job_id'), str):
            return jsonify(error='Approve your base avatar to continue.'), 400
        if any(j['id']==body['job_id'] and j.get('rejected') for j in fashn.public_jobs(session['owner'])):
            return jsonify(error='This candidate was rejected'),400
        try:
            app.extensions['avatar_activate'](session['owner'], body['job_id'])
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(ok=True)

    @app.get('/api/fashn/images/<job_id>')
    def fashn_image(job_id):
        image = fashn.image(session['owner'], job_id)
        if image is None:
            abort(404)
        return send_file(io.BytesIO(image), mimetype='image/png', download_name='weatheravatar.png')

    @app.post('/api/pilot/photo')
    def upload():
        file = request.files.get('photo')
        try:
            photo = normalize_photo(file.read() if file else b'')
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with lock:
            record = state.get(session['owner'])
            if record and record['jobs']:
                return jsonify(error='Clear this session before changing its reference photo.'), 409
            if not record and len(state) >= 16:
                return jsonify(error='Local session limit reached. Restart the pilot.'), 429
            state[session['owner']] = {'photo': photo, 'jobs': [], 'requests': {}, 'avatars': [], 'active_avatar': None}
            store.save(session['owner'], state[session['owner']])
        return jsonify(ok=True)

    @app.get('/api/pilot/photo')
    def reference():
        with lock:
            photo = owned()['photo']
        return send_file(io.BytesIO(photo), mimetype='image/jpeg')

    def work(owner, job):
        with lock:
            record = state.get(owner)
            if not record or job not in record['jobs']:
                return
            photo = record['photo']
            avatar = next((a for a in record['avatars'] if a['id'] == job.get('avatar_id')), None)
            if job['mode'] in {'avatar', 'protected', 'clothes'}:
                photo = next(j['image'] for j in record['jobs'] if j['id'] == avatar['source_job'])
            job['status'] = 'generating'
            store.save(owner, record)
        started = time.monotonic()
        update = {}
        try:
            extra = {'clothing_regions': avatar['clothing_regions'][job['scenario']]} if job['mode'] == 'clothes' else {}
            image, usage = renderer(photo, job['scenario'], job['quality'], mode=job['mode'],
                                    preferences=job.get('preferences', ''),
                                    head_box=avatar['head_box'] if avatar else None, **extra)
            update.update(usage=usage, estimated_usd=estimated_cost(usage))
            with Image.open(io.BytesIO(image)) as output:
                output.load()
                if output.size != (1024, 1536):
                    raise ValueError('Unexpected output dimensions.')
            checks = {'dimensions_match': True, 'body_alignment': 'requires human review'}
            if job['mode'] == 'protected':
                image, checks = preserve_head(photo, image, avatar['head_box'])
            if job['mode'] == 'clothes':
                image, checks = compose_clothes(photo, image, avatar['clothing_regions'][job['scenario']])
            update.update(status='done', image=image, checks=checks)
        except requests.Timeout:
            update.update(status='failed', error='Request timed out. Billing may still occur. No automatic retry was made.')
        except RuntimeError as exc:
            update.update(status='failed', error=str(exc))
        except Exception:
            update.update(status='failed', error='Generation failed or returned an invalid frame. Billing may still occur. No automatic retry was made.')
        with lock:
            if state.get(owner) is record:
                job.update(update, seconds=round(time.monotonic()-started, 1))
                store.save(owner, record)

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error=error.description), 400

    def request_body():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description='Expected a JSON object.')
        return body

    def queue(record, specs, request_id):
        nonlocal submitted
        owner = session['owner']
        if request_id in record['requests']:
            return jsonify(ids=record['requests'][request_id], reused=True), 200
        jobs, ids = [], []
        for spec in specs:
            existing = next((j for j in reversed(record['jobs'])
                             if spec.get('cache_key') and j.get('cache_key') == spec['cache_key']
                             and j['status'] in {'done', 'queued', 'generating'} and j.get('rating', {}).get('accepted') is not False), None)
            if existing:
                ids.append(existing['id'])
                continue
            job = dict(id=secrets.token_hex(12), status='queued', model=MODEL, size='1024x1536',
                       renderer_version=RENDERER_VERSION, pose=POSE, rating={}, created_at=time.time(),
                       output_estimate_usd=OUTPUT_PRICES[spec['quality']], pricing_date=PRICING_DATE, **spec)
            jobs.append(job)
            ids.append(job['id'])
        if jobs and any(j['status'] in {'queued', 'generating'} for r in state.values() for j in r['jobs']):
            return jsonify(error='A different comparison is already running. Wait for it to finish.'), 409
        if submitted + len(jobs) > 24:
            return jsonify(error='The local pilot has reached its persistent 24-image allowance. Cached portraits remain available.'), 429
        if jobs and not os.environ.get('OPENAI_API_KEY'):
            return jsonify(error='Launch the pilot through the credential broker first.'), 503
        record['jobs'].extend(jobs)
        record['requests'][request_id] = ids
        submitted += len(jobs)
        store.save(owner, record, submitted)
        for job in jobs:
            pool.submit(work, owner, job)
        return jsonify(ids=ids, generated=len(jobs), reused=len(ids)-len(jobs)), 202 if jobs else 200

    def authorized(body):
        rid = body.get('request_id')
        return body.get('consent') is True and isinstance(rid, str) and 8 <= len(rid) <= 80

    @app.post('/api/pilot/avatar')
    def candidate():
        body = request_body()
        preferences = body.get('preferences', '')
        quality = body.get('quality', 'medium')
        if not authorized(body) or not isinstance(preferences, str) or len(preferences) > 500 or not isinstance(quality, str) or quality not in OUTPUT_PRICES:
            return jsonify(error='Photo consent, valid quality and preferences under 500 characters are required.'), 400
        with lock:
            return queue(owned(), [dict(mode='base', kind='avatar', scenario='sun', quality=quality,
                                      preferences=preferences, prompt=base_prompt(preferences))], body['request_id'])

    @app.post('/api/pilot/approve')
    def approve():
        body = request_body()
        if not valid_box(body.get('head_box')) or body.get('approved') is not True:
            return jsonify(error='Review the reference and set a protected head region before approving.'), 400
        with lock:
            record = owned()
            job = next((j for j in record['jobs'] if j['id'] == body.get('job_id') and j['status'] == 'done' and j.get('kind') == 'avatar'), None)
            if not job:
                abort(404)
            existing = next((a for a in record['avatars'] if a['source_job'] == job['id']), None)
            if existing:
                return jsonify(avatar=existing)
            avatar = dict(id=secrets.token_hex(12), version=len(record['avatars'])+1, source_job=job['id'],
                          head_box=body['head_box'], preferences=job['preferences'], pose=POSE, approved_at=time.time())
            record['avatars'].append(avatar)
            record['active_avatar'] = avatar['id']
            store.save(session['owner'], record)
            return jsonify(avatar=avatar)

    @app.post('/api/pilot/runs')
    def run():
        body = request_body()
        scenario, qualities = body.get('scenario'), body.get('qualities')
        modes = body.get('modes', ['selfie'])
        def choices(values, allowed):
            return isinstance(values, list) and 1 <= len(values) <= 3 and all(isinstance(v, str) and v in allowed for v in values) and len(set(values)) == len(values)
        if not isinstance(scenario, str) or scenario not in SCENARIOS or not choices(qualities, OUTPUT_PRICES) or not choices(modes, MODES) or len(modes)*len(qualities) > 3:
            return jsonify(error='Select at most three method × quality combinations.'), 400
        if not authorized(body):
            return jsonify(error='Photo consent and a valid request ID are required.'), 400
        with lock:
            record = owned()
            avatar_id = body.get('avatar_id', record.get('active_avatar'))
            avatar = next((a for a in record['avatars'] if a['id'] == avatar_id), None)
            if any(m != 'selfie' for m in modes) and not avatar:
                return jsonify(error='Approve a full-body avatar before comparing editing methods.'), 409
            specs = [dict(kind='outfit', mode=m, scenario=scenario, quality=q, avatar_id=avatar['id'] if avatar else None,
                          outfit=outfit_spec(scenario), prompt=edit_prompt(SCENARIOS[scenario][2], m),
                          cache_key=cache_key(avatar['id'] if avatar else 'original-selfie', scenario, m, q))
                     for m in modes for q in qualities]
            return queue(record, specs, body['request_id'])

    @app.post('/api/pilot/dress')
    def dress():
        body = request_body()
        scenario = body.get('scenario')
        if not isinstance(scenario, str) or scenario not in SCENARIOS or not authorized(body):
            return jsonify(error='Choose weather and confirm generation.'), 400
        with lock:
            record = owned()
            avatar = next((a for a in record['avatars'] if a['id'] == record.get('permanent_avatar')), None)
            if not avatar or not avatar.get('clothing_regions'):
                return jsonify(error='Your permanent avatar is not ready yet.'), 409
            spec = dict(kind='outfit', mode='clothes', scenario=scenario, quality='medium',
                        avatar_id=avatar['id'], outfit=outfit_spec(scenario),
                        prompt=edit_prompt(SCENARIOS[scenario][2], 'clothes'),
                        cache_key=cache_key(avatar['id'], scenario, 'clothes', 'medium', avatar.get('region_version')))
            return queue(record, [spec], body['request_id'])

    @app.get('/api/pilot/images/<job_id>')
    def result_image(job_id):
        with lock:
            job = next((j for j in owned()['jobs'] if j['id'] == job_id and j['status'] == 'done'), None)
            if not job:
                abort(404)
            image = job['image']
        return send_file(io.BytesIO(image), mimetype='image/png', download_name='weatheravatar.png')

    @app.post('/api/pilot/ratings/<job_id>')
    def rate(job_id):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error='Expected a JSON object.'), 400
        if any(type(body.get(k)) is not int or not 1 <= body[k] <= 5 for k in ('likeness', 'outfit', 'body', 'framing', 'garment', 'boundary')) or type(body.get('accepted')) is not bool:
            return jsonify(error='Choose likeness and outfit scores from 1 to 5.'), 400
        with lock:
            job = next((j for j in owned()['jobs'] if j['id'] == job_id and j['status'] == 'done'), None)
            if not job:
                abort(404)
            job['rating'] = {k: body[k] for k in ('likeness', 'outfit', 'body', 'framing', 'garment', 'boundary', 'accepted')}
            store.save(session['owner'], owned())
        return jsonify(ok=True)

    @app.delete('/api/pilot')
    def clear():
        with lock:
            record = state.get(session['owner'], {})
            if any(j['status'] in {'queued', 'generating'} for j in record.get('jobs', [])):
                return jsonify(error='Wait for generation to finish before clearing the session.'), 409
            fashn.delete(session['owner'])
            state.pop(session['owner'], None)
            store.delete(session['owner'])
            with store.db: store.db.execute('DELETE FROM garments WHERE owner=?',(session['owner'],))
            store.db.execute('DELETE FROM weather_profiles WHERE owner=?',(session['owner'],))
            store.db.execute('DELETE FROM avatar_profiles WHERE owner=?',(session['owner'],))
        return jsonify(ok=True)

    @app.get('/api/pilot/export')
    def export():
        with lock:
            jobs = [public(j) for j in owned()['jobs']]
            avatars = owned()['avatars']
        response = jsonify(model=MODEL, pricing_date=PRICING_DATE, currency='USD',
                           cost_method='Undiscounted token estimate; not an invoice. Failed requests may have unknown charges.',
                           avatars=avatars, jobs=jobs, release_target='90% first-attempt acceptance; not yet validated',
                           limitations='Generic garments, human body/framing checks, one model. No cross-provider or population validation.')
        response.headers['Content-Disposition'] = 'attachment; filename=weatheravatar-comparison.json'
        return response

    # Start the worker only after all tables/routes finish initialization.
    fashn.autostart = fashn_autostart
    fashn.kick()
    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.environ.get('PILOT_PORT', '5076')), debug=False, threaded=True)
