"""FASHN Edit adapter and durable local job ledger. No credentials in storage."""
import base64
import hashlib
import io
import json
import math
import os
import re
import secrets
import threading
import time

import requests
from PIL import Image

SETTINGS = dict(resolution='2k', generation_mode='balanced', seed=42,
                num_images=1, output_format='png', return_base64=True)
VERSION = 'fashn-edit-v1'
OUTFIT_VERSION = 'max-reviewed-v1'
EXPECTED_CREDITS = 3
BASE_PROMPT = ('Create a photorealistic full-length studio portrait of this same person. '
               'Preserve their facial likeness, age, skin tone and hairstyle. Natural adult '
               'human proportions, relaxed upright stance, arms at sides. Gray plain T-shirt, '
               'khaki trousers, black sneakers. Neutral warm studio background. Entire head, '
               'hands and shoes visible with generous space on every edge. No caricature.')


class Rejected(Exception):
    pass


class FashnClient:
    def __init__(self):
        if os.environ.get('FASHN_DNS_MODE') == 'encrypted':
            from fashn_transport import encrypted_session
            self.http = encrypted_session()
        else:
            self.http = requests

    @property
    def ready(self):
        return bool(os.environ.get('FASHN_API_KEY'))

    def headers(self):
        return {'Authorization': 'Bearer ' + os.environ['FASHN_API_KEY']}

    def submit(self, image, prompt):
        with Image.open(io.BytesIO(image)) as source:
            mime = Image.MIME[source.format]
        response = self.http.post('https://api.fashn.ai/v1/run', headers=self.headers(),
            json={'model_name': 'edit', 'inputs': dict(SETTINGS, prompt=prompt,
                  image=f'data:{mime};base64,' + base64.b64encode(image).decode())},
            timeout=(60, 90), allow_redirects=False)
        if 400 <= response.status_code < 500:
            raise Rejected('FASHN rejected the request. Check API access, balance and rate limits.')
        response.raise_for_status()
        prediction = response.json().get('id')
        if not isinstance(prediction, str) or not re.fullmatch(r'[\w-]{1,160}', prediction):
            raise ValueError('Missing prediction ID')
        return prediction

    def submit_tryon(self, image, product, prompt=None):
        def uri(raw):
            with Image.open(io.BytesIO(raw)) as im:mime=Image.MIME[im.format]
            return 'data:'+mime+';base64,'+base64.b64encode(raw).decode()
        response=self.http.post('https://api.fashn.ai/v1/run',headers=self.headers(),json={
            'model_name':'tryon-max','inputs':dict(SETTINGS,model_image=uri(image),product_image=uri(product),
            prompt=prompt or 'Wear this exact product. Preserve the same person, face, pose, framing, and all other clothing. Keep the whole person and shoes visible.')},timeout=(60,90),allow_redirects=False)
        if 400<=response.status_code<500:raise Rejected('FASHN rejected the request. Check API access, balance and rate limits.')
        response.raise_for_status();prediction=response.json().get('id')
        if not isinstance(prediction,str) or not re.fullmatch(r'[\w-]{1,160}',prediction):raise ValueError('Missing prediction ID')
        return prediction

    def poll(self, prediction):
        response = self.http.get('https://api.fashn.ai/v1/status/' + prediction,
                                headers=self.headers(), timeout=(10, 30), allow_redirects=False)
        response.raise_for_status()
        result = response.json()
        credit = response.headers.get('x-fashn-credits-used')
        try:
            credit = float(credit)
            if not math.isfinite(credit) or credit < 0:
                credit = None
        except (TypeError, ValueError):
            credit = None
        return result, credit


def decode_output(value):
    if not isinstance(value, str) or not value.startswith('data:image/png;base64,') or len(value) > 45_000_000:
        raise ValueError('Expired or invalid image')
    raw = base64.b64decode(value.split(',', 1)[1], validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG' or min(image.size) < 256 or image.width * image.height > 20_000_000:
            raise ValueError('Invalid image dimensions')
        image.load()
        dimensions = image.size
    return raw, dimensions


class FashnJobs:
    """One local process. Transactions reserve credits before any network operation."""
    def __init__(self, db, lock, client=None, autostart=True, user_limit=12, global_limit=24):
        self.db, self.lock = db, lock
        self.client = client or FashnClient()
        self.autostart = autostart
        self.user_limit, self.global_limit = user_limit, global_limit
        self.thread = None
        self.stop = threading.Event()
        from outfit_quality import OutfitReviewer
        self.reviewer = OutfitReviewer()
        with lock, db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS fashn_jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, cache TEXT NOT NULL,
                status TEXT NOT NULL, prediction TEXT, charge REAL NOT NULL,
                metadata TEXT NOT NULL, source BLOB, image BLOB, deleted INTEGER DEFAULT 0,
                UNIQUE(owner, cache));
              CREATE TABLE IF NOT EXISTS fashn_avatars (owner TEXT PRIMARY KEY, job TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS fashn_external_spend (id TEXT PRIMARY KEY, owner TEXT NOT NULL, credits REAL NOT NULL);
            ''')
            db.execute("UPDATE fashn_jobs SET status='unknown' WHERE status='submitting'")
            db.execute("UPDATE fashn_jobs SET status='reviewing' WHERE status='checking'")
        if 'product' not in {r[1] for r in db.execute('PRAGMA table_info(fashn_jobs)')}:
            with lock,db:db.execute('ALTER TABLE fashn_jobs ADD COLUMN product BLOB')
        self.kick()

    def spent(self, owner=None):
        clause=' WHERE owner=?' if owner is not None else ''
        args=(owner,) if owner is not None else ()
        return (self.db.execute('SELECT COALESCE(SUM(charge),0) FROM fashn_jobs'+clause,args).fetchone()[0]+
                self.db.execute('SELECT COALESCE(SUM(credits),0) FROM fashn_external_spend'+clause,args).fetchone()[0])

    def kick(self):
        with self.lock:
            if self.autostart and (not self.thread or not self.thread.is_alive()) and self.client.ready:
                self.thread = threading.Thread(target=self.run, daemon=True)
                self.thread.start()

    def run(self):
        while not self.stop.is_set():
            if not self.tick():
                return
            self.stop.wait(5)

    def public_jobs(self, owner):
        with self.lock:
            return [dict(json.loads(meta), id=id_, status=status, credits_reserved_or_used=charge)
                    for id_, status, charge, meta in self.db.execute(
                        'SELECT id,status,charge,metadata FROM fashn_jobs WHERE owner=? AND deleted=0 ORDER BY rowid', (owner,))]

    def approved(self, owner):
        with self.lock:
            row = self.db.execute('SELECT job FROM fashn_avatars WHERE owner=?', (owner,)).fetchone()
            return row[0] if row else None

    def image(self, owner, job):
        with self.lock:
            row = self.db.execute("SELECT image FROM fashn_jobs WHERE owner=? AND id=? AND status='done' AND deleted=0", (owner, job)).fetchone()
            return row[0] if row else None

    def import_studio(self, owner, raw, kind='base', scenario='', avatar=None):
        """Import a user-approved original PNG; never count Studio exports as API usage."""
        raw, size = decode_output('data:image/png;base64,' + base64.b64encode(raw).decode())
        if kind not in {'base', 'outfit'} or (kind == 'outfit' and (not avatar or scenario not in {'sun', 'rain', 'cold'})):
            raise ValueError('Invalid Studio asset.')
        cache = 'studio:' + hashlib.sha256(raw + json.dumps([kind, scenario, avatar]).encode()).hexdigest()
        with self.lock, self.db:
            existing = self.db.execute('SELECT id FROM fashn_jobs WHERE owner=? AND cache=? AND deleted=0', (owner, cache)).fetchone()
            if existing:
                return existing[0]
            if kind == 'outfit' and not self.image(owner, avatar):
                raise ValueError('Import the base first.')
            id_ = secrets.token_hex(12)
            meta = dict(provider='fashn', model='edit', version=VERSION, provenance='studio-original-export',
                        kind=kind, scenario=scenario, avatar_id=avatar, dimensions=list(size),
                        created_at=time.time(), actual_credits=None, expected_credits=0,
                        imported=True, billing_note='Existing Studio export; no API request or API charge.')
            self.db.execute('INSERT INTO fashn_jobs(id,owner,cache,status,charge,metadata,image) VALUES(?,?,?,?,?,?,?)',
                            (id_, owner, cache, 'done', 0, json.dumps(meta), raw))
        return id_

    def approve(self, owner, job):
        with self.lock, self.db:
            row = self.db.execute("SELECT metadata FROM fashn_jobs WHERE owner=? AND id=? AND status='done' AND deleted=0", (owner, job)).fetchone()
            if not row or json.loads(row[0])['kind'] != 'base':
                raise ValueError('Choose a completed base avatar.')
            self.db.execute('INSERT OR REPLACE INTO fashn_avatars VALUES (?,?)', (owner, job))

    def enqueue(self, owner, source, kind, scenario='', avatar=None, outfit='', wardrobe_signature=None, product=None, garment_ids=None, parent_look_id=None, full_outfit=False):
        prompt = (BASE_PROMPT + (' Create an alternative portrait, variation '+str(avatar)+'.' if avatar else '')) if kind == 'base' else (
            'Edit only the clothes on this same person: ' + outfit +
            ' Keep the same facial identity, hairstyle, body proportions, pose, hands, camera, '
            'background and framing. Keep the full person including shoes in frame. Natural '
            'photorealistic clothing. Do not restyle the face or change the body.')
        cache = hashlib.sha256(json.dumps([VERSION, SETTINGS, kind, scenario, avatar,
                    hashlib.sha256(source).hexdigest(), prompt] + ([hashlib.sha256(product).hexdigest()] if product else []), sort_keys=True).encode()).hexdigest()
        if full_outfit:
            cache = 'reviewed:' + hashlib.sha256(json.dumps([OUTFIT_VERSION, SETTINGS, avatar, hashlib.sha256(source).hexdigest(), hashlib.sha256(product).hexdigest()],sort_keys=True).encode()).hexdigest()
        with self.lock, self.db:
            existing = self.db.execute('SELECT id,deleted FROM fashn_jobs WHERE owner=? AND cache=?', (owner, cache)).fetchone()
            if existing:
                if existing[1]:
                    raise ValueError('This request was deleted. Start a new local session to create it again.')
                return existing[0], True
            if not self.client.ready:
                raise ValueError('FASHN API access is not configured. Add FASHN_API_KEY on the server; Studio credits are separate.')
            total = self.spent()
            used = self.spent(owner)
            if total + EXPECTED_CREDITS > self.global_limit or used + EXPECTED_CREDITS > self.user_limit:
                raise ValueError('The app’s local spending limit is reached; this is not your FASHN account balance. No new generation was submitted.')
            id_ = secrets.token_hex(12)
            meta = dict(provider='fashn', model='edit', version=VERSION, settings=SETTINGS,
                        kind=kind, scenario=scenario, avatar_id=avatar, prompt=prompt, wardrobe_signature=wardrobe_signature,
                        created_at=time.time(), expected_credits=EXPECTED_CREDITS, actual_credits=None)
            self.db.execute('INSERT INTO fashn_jobs(id,owner,cache,status,charge,metadata,source) VALUES(?,?,?,?,?,?,?)',
                            (id_, owner, cache, 'queued', EXPECTED_CREDITS, json.dumps(meta), source))
            if product:
                meta.update(model='tryon-max',preview=True,accepted=False,garment_ids=garment_ids or {},parent_look_id=parent_look_id,full_outfit=full_outfit)
                if full_outfit:meta.update(pipeline=OUTFIT_VERSION,repair_count=0,incurred_credits=0,reference_hash=hashlib.sha256(product).hexdigest(),quality_state='generating')
                self.db.execute('UPDATE fashn_jobs SET product=?,metadata=? WHERE id=?',(product,json.dumps(meta),id_))
        self.kick()
        return id_, False

    def tick(self):
        with self.lock:
            row = self.db.execute("SELECT id,status,prediction,metadata,source,deleted,product FROM fashn_jobs WHERE status IN ('polling','reviewing') OR (status='queued' AND (SELECT COUNT(*) FROM fashn_jobs WHERE status IN ('submitting','polling'))<2) ORDER BY CASE status WHEN 'reviewing' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, COALESCE(json_extract(metadata,'$.last_poll_at'),0),rowid LIMIT 1").fetchone()
            if not row or not self.client.ready:
                return False
            id_, status, prediction, text, source, deleted, product = row
            meta = json.loads(text)
            if status == 'polling':
                meta['last_poll_at']=time.time()
                with self.db:self.db.execute('UPDATE fashn_jobs SET metadata=? WHERE id=?',(json.dumps(meta),id_))
            if status == 'queued':
                with self.db:
                    self.db.execute("UPDATE fashn_jobs SET status='submitting' WHERE id=?", (id_,))
        if status == 'reviewing':
            self.review_outfit(id_,meta,product)
            return True
        if status == 'queued':
            try:
                if meta.get('repair_crop'):
                    from outfit_quality import crop_reference
                    product=crop_reference(product,meta['repair_crop'])
                prediction = (self.client.submit_tryon(source,product,prompt=meta.get('repair_prompt',meta['prompt'])) if meta.get('full_outfit') else self.client.submit_tryon(source,product)) if product else self.client.submit(source, meta['prompt'])
            except Rejected as exc:
                self.finish(id_, 'failed', meta, charge=meta.get('incurred_credits',0), error=str(exc))
            except Exception as exc:
                meta['failure_type'] = type(exc).__name__
                meta['transport_timeout'] = 'timed out' in str(exc).lower()
                meta['dns_failure'] = 'dns' in str(exc).lower()
                self.finish(id_, 'unknown', meta, error='Submission outcome unknown. Credits remain reserved; no automatic resubmission. Check the FASHN dashboard.')
            else:
                with self.lock, self.db:
                    self.db.execute("UPDATE fashn_jobs SET status='polling',prediction=?,source=NULL,product=CASE WHEN json_extract(metadata,'$.pipeline') IS NOT NULL THEN product ELSE NULL END WHERE id=?", (prediction, id_))
            return True
        try:
            result, credits = self.client.poll(prediction)
            meta.pop('error', None)
            if result.get('status') == 'failed':
                self.finish(id_, 'failed', meta, charge=meta.get('incurred_credits',0), error='FASHN could not generate this look. No automatic paid retry.')
            elif result.get('status') == 'completed':
                if meta.get('pipeline'):
                    credits=meta.get('incurred_credits',0)+(credits if credits is not None else EXPECTED_CREDITS)
                meta['actual_credits'] = credits
                try:
                    raw, size = decode_output(result.get('output', [None])[0])
                    meta['dimensions'] = list(size)
                except Exception:
                    self.finish(id_, 'unavailable', meta, charge=credits,
                                error='FASHN completed, but its image is expired or invalid. No regeneration was charged by this app.')
                else:
                    if meta.get('pipeline') and not deleted:
                        meta.update(incurred_credits=credits,quality_state='checking')
                        with self.lock,self.db:
                            self.db.execute("UPDATE fashn_jobs SET status='reviewing',metadata=?,charge=?,image=? WHERE id=? AND deleted=0",(json.dumps(meta),credits,raw,id_))
                    else:self.finish(id_, 'done', meta, charge=credits, image=raw)
        except Exception:
            # GET is safe to retry. Never expose provider bodies or credential-bearing errors.
            meta['error'] = 'Waiting for FASHN status. Polling will resume automatically; no new generation is submitted.'
            with self.lock, self.db:
                self.db.execute('UPDATE fashn_jobs SET metadata=? WHERE id=?', (json.dumps(meta), id_))
        return True

    def review_outfit(self, id_, meta, product):
        with self.lock:
            row=self.db.execute('SELECT owner,image,deleted FROM fashn_jobs WHERE id=?',(id_,)).fetchone()
            owner,raw,deleted=row
            if deleted:
                self.finish(id_,'cancelled',meta);return
            with self.db:self.db.execute("UPDATE fashn_jobs SET status='checking' WHERE id=?",(id_,))
        try:
            verdict=self.reviewer.review(self.image(owner,meta['avatar_id']),product,raw)
            meta.setdefault('reviews',[]).append(verdict)
            if verdict['face_and_frame_ok'] and verdict['clothing_ok']:
                meta.update(accepted=True,preview=False,quality_state='passed')
                self.finish(id_,'done',meta,image=raw);return
            if not verdict['face_and_frame_ok']:
                meta['quality_state']='needs_review'
                meta['quality_note']='Face or framing changed. This preview was not saved automatically.'
            elif meta['repair_count']>=2:
                meta['quality_state']='needs_review'
                meta['quality_note']='The outfit still differs after two repairs. Review this preview before saving.'
            else:
                from outfit_quality import crop_reference
                crop_reference(product,verdict['crop'])  # Validate before reserving another charge.
                with self.lock,self.db:
                    if self.db.execute('SELECT deleted FROM fashn_jobs WHERE id=?',(id_,)).fetchone()[0]:return
                    total=self.spent()
                    used=self.spent(owner)
                    if total+3>self.global_limit or used+3>self.user_limit:raise ValueError('Repair budget unavailable')
                    meta['repair_count']+=1
                    meta.update(quality_state='repairing',repair_crop=verdict['crop'],repair_prompt=
                        'Correct only these clothing differences using the reference crop: '+verdict['repair_instruction'][:1800]+
                        ' Preserve the same face, hair, proportions, pose, background, camera and full head-to-shoe framing. Keep all already correct garments unchanged.')
                    self.db.execute("UPDATE fashn_jobs SET status='queued',prediction=NULL,charge=charge+3,metadata=?,source=? WHERE id=?",(json.dumps(meta),raw,id_))
                return
        except Exception:
            meta.update(quality_state='needs_review',quality_note='Automatic review or repair is unavailable. Your preview is kept; no further generation will run.')
        self.finish(id_,'done',meta,image=raw)

    def finish(self, id_, status, meta, charge=None, image=None, error=None):
        if error:
            meta['error'] = error
        with self.lock, self.db:
            if meta.get('pipeline') and status in ('failed','unavailable') and image is None:
                previous=self.db.execute('SELECT image FROM fashn_jobs WHERE id=? AND deleted=0',(id_,)).fetchone()
                if previous and previous[0]:
                    image=previous[0];status='done'
                    meta.update(quality_state='needs_review',quality_note=error or 'Repair failed. Previous preview retained.')
            self.db.execute('UPDATE fashn_jobs SET status=?,metadata=?,charge=COALESCE(?,charge),source=NULL,product=NULL,image=CASE WHEN deleted=0 THEN ? ELSE NULL END WHERE id=?',
                            (status, json.dumps(meta), charge, image, id_))

    def delete(self, owner):
        with self.lock, self.db:
            self.db.execute('DELETE FROM fashn_avatars WHERE owner=?', (owner,))
            # Retain only the cost ledger and IDs for reconciliation, never resurrect pictures.
            self.db.execute("UPDATE fashn_jobs SET deleted=1,source=NULL,product=NULL,image=NULL,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,charge=CASE WHEN status='queued' THEN COALESCE(json_extract(metadata,'$.incurred_credits'),0) ELSE charge END WHERE owner=?", (owner,))
