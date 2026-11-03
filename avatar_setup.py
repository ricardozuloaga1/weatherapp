"""Approve avatars, retain per-avatar preferences, and select photographic outfits."""
import json,time,hashlib
from pathlib import Path
from flask import request,session,jsonify
from weather_live import CATALOG,signature

STARTERS = json.loads(Path(__file__).with_name('outfit_catalog.json').read_text())
KEYS=('wardrobe','wardrobe_complete','weather_outfits','weather_options','preferred_looks','auto_generation')
def register_setup(app,store,lock,jobs,profile):
    with lock,store.db:store.db.execute('CREATE TABLE IF NOT EXISTS avatar_profiles(owner TEXT NOT NULL,avatar TEXT NOT NULL,name TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,avatar))')
    save=app.extensions['weather_profile_save']
    def remember(owner,avatar):
        if not avatar:return
        p=profile(owner);body={k:p[k] for k in KEYS if k in p}
        with store.db:
            store.db.execute('INSERT OR IGNORE INTO avatar_profiles VALUES(?,?,?,?,?)',(owner,avatar,'My avatar',json.dumps(body),time.time()))
            store.db.execute('UPDATE avatar_profiles SET body=? WHERE owner=? AND avatar=?',(json.dumps(body),owner,avatar))
    def activate(owner,avatar,name=None):
        with lock:
            candidate=next((j for j in jobs.public_jobs(owner) if j['id']==avatar and j['kind']=='base' and j['status']=='done' and not j.get('rejected')),None)
            if not candidate:raise ValueError('Choose a completed avatar preview.')
            old=jobs.approved(owner)
            remember(owner,old)
            row=store.db.execute('SELECT body FROM avatar_profiles WHERE owner=? AND avatar=?',(owner,avatar)).fetchone()
            p=profile(owner)
            for key in KEYS:p.pop(key,None)
            p.update(json.loads(row[0]) if row else {'auto_generation':False})
            with store.db:
                jobs.approve(owner,avatar);save(owner,p);remember(owner,avatar)
                if name:store.db.execute('UPDATE avatar_profiles SET name=? WHERE owner=? AND avatar=?',(name[:60],owner,avatar))
    def reference(owner,choice):
        if not isinstance(choice,dict) or choice.get('kind') not in ('look','garment','starter') or not isinstance(choice.get('id'),str):raise ValueError('Choose an outfit photograph for each weather type.')
        if choice['kind']=='starter':
            if choice['id'] in STARTERS:return (Path(app.static_folder)/'images'/'outfits'/(choice['id']+'.jpg')).read_bytes()
            raise ValueError('Choose an available starter outfit.')
        if choice['kind']=='look':
            j=next((j for j in jobs.public_jobs(owner) if j['id']==choice['id'] and j['kind']=='outfit' and j['status']=='done' and (not j.get('preview') or j.get('accepted'))),None)
            if j:return jobs.image(owner,j['id'])
        else:
            row=store.db.execute("SELECT image FROM garments WHERE owner=? AND id=? AND category='outfit'",(owner,choice['id'])).fetchone()
            if row:return row[0]
        raise ValueError('This outfit photo is unavailable. Select another one.')
    def saved_for_choice(owner,base,choice):
        product=reference(owner,choice)
        digest=hashlib.sha256(product).hexdigest()
        candidates=jobs.public_jobs(owner)
        return next((j for j in reversed(candidates) if j.get('avatar_id')==base and j['status']=='done'
            and j.get('accepted') and j.get('reference_hash')==digest),None)
    def weather_matches(owner, pending=False):
        p=profile(owner);base=jobs.approved(owner);matches={}
        for scenario,choice in p.get('weather_outfits',{}).items():
            try:
                saved=saved_for_choice(owner,base,choice)
                if pending:
                    digest=hashlib.sha256(reference(owner,choice)).hexdigest()
                    saved=next((j for j in reversed(jobs.public_jobs(owner)) if j.get('avatar_id')==base and j.get('pipeline') and j.get('reference_hash')==digest and not j.get('accepted')),None)
                if not pending and not saved and choice['kind']=='look':
                    saved=next((j for j in jobs.public_jobs(owner) if j['id']==choice['id'] and j.get('avatar_id')==base and j['status']=='done' and (not j.get('preview') or j.get('accepted'))),None)
                if saved:matches[scenario]=saved['id']
            except ValueError:pass
        return matches
    app.extensions['weather_matches']=weather_matches
    def enqueue_weather(owner,scenario):
        p=profile(owner);base=jobs.approved(owner);choice=p.get('weather_outfits',{}).get(scenario)
        if not base or not p.get('wardrobe_complete'):raise ValueError('Approve an avatar and save your wardrobe first.')
        product=reference(owner,choice)
        saved=saved_for_choice(owner,base,choice)
        if saved:return saved['id'],True
        if choice['kind']=='look':
            existing=next((j for j in jobs.public_jobs(owner) if j['id']==choice['id'] and j.get('avatar_id')==base),None)
            if existing:return existing['id'],True
        return jobs.enqueue(owner,jobs.image(owner,base),'outfit',scenario,base,'Transfer the visible clothing from the reference photograph: top, trousers or skirt, outerwear, and shoes if visible. If shoes or any garment are outside the reference frame, preserve those from the model image. Do not copy text, logos added as captions, or the reference person. Keep only the model image person and identity.',signature(p,scenario),product=product,garment_ids={'outfit':choice['id']} if choice['kind']=='garment' else {},parent_look_id=base,full_outfit=True)
    @app.get('/api/setup')
    def get_setup():
        owner=session['owner']
        with lock:
            remember(owner,jobs.approved(owner))
            profiles=[dict(avatar=r[0],name=r[1],complete=json.loads(r[2]).get('wardrobe_complete',False)) for r in store.db.execute('SELECT avatar,name,body FROM avatar_profiles WHERE owner=? ORDER BY created',(owner,))]
        choices=[dict(kind='look',id=j['id'],name=CATALOG.get(j['scenario'],{}).get('label','Saved outfit'),scenario=j['scenario'],image='/api/fashn/images/'+j['id']+'/detail/outfit',source='Clothes from a saved look') for j in jobs.public_jobs(owner) if j['kind']=='outfit' and j['status']=='done' and (not j.get('preview') or j.get('accepted'))]
        with lock:
            choices += [dict(kind='garment',id=r[0],name=r[1],image='/api/garments/'+r[0]+'/image',source='Your outfit photograph') for r in store.db.execute("SELECT id,name FROM garments WHERE owner=? AND category='outfit'",(owner,))]
        choices += [dict(kind='starter',id=k,image='/static/images/outfits/'+k+'.jpg',source='UNIQLO · outfit reference',**v) for k,v in STARTERS.items()]
        return jsonify(profiles=profiles,choices=choices,active=jobs.approved(owner))
    @app.post('/api/setup/approve')
    def setup_approve():
        b=request.get_json(silent=True)
        if not isinstance(b,dict) or b.get('approved') is not True:return jsonify(error='Confirm this avatar looks right.'),400
        name=b.get('name','')
        if not isinstance(name,str):return jsonify(error='Enter a profile name.'),400
        try:activate(session['owner'],b.get('id'),name.strip())
        except ValueError as e:return jsonify(error=str(e)),400
        return jsonify(ok=True)
    @app.post('/api/setup/switch')
    def setup_switch():
        b=request.get_json(silent=True) or {};owner=session['owner'];id_=b.get('id') if isinstance(b,dict) else None
        with lock:row=store.db.execute('SELECT 1 FROM avatar_profiles WHERE owner=? AND avatar=?',(owner,id_)).fetchone()
        if not row:return jsonify(error='Choose one of your approved profiles.'),400
        activate(owner,id_);return jsonify(ok=True)
    @app.post('/api/setup/wardrobe')
    def setup_wardrobe():
        b=request.get_json(silent=True);owner=session['owner']
        if not isinstance(b,dict) or not isinstance(b.get('choices'),dict) or set(b['choices'])!=set(CATALOG):return jsonify(error='Choose an outfit for all six weather types.'),400
        with lock:
            if not jobs.approved(owner):return jsonify(error='Approve your avatar first.'),400
            try:
                options={}
                for weather, value in b['choices'].items():
                    values=value if isinstance(value,list) else [value]
                    if not 1<=len(values)<=40:raise ValueError('Choose between 1 and 40 looks for each weather type.')
                    options[weather]=[]
                    for choice in values:
                        reference(owner,choice)
                        clean={'kind':choice['kind'],'id':choice['id']}
                        if clean not in options[weather]:options[weather].append(clean)
            except ValueError as e:return jsonify(error=str(e)),400
            p=profile(owner);p['weather_options']=options;p['weather_outfits']={k:p.get('weather_outfits',{}).get(k) if p.get('weather_outfits',{}).get(k) in v else v[0] for k,v in options.items()};p['wardrobe_complete']=True;p['auto_generation']=False
            save(owner,p);remember(owner,jobs.approved(owner))
        return jsonify(ok=True)
    @app.post('/api/setup/another')
    def another():
        b=request.get_json(silent=True) or {};owner=session['owner']
        if not isinstance(b,dict) or b.get('consent') is not True:return jsonify(error='Confirm creating another look if needed.'),400
        scenario=b.get('scenario')
        if not isinstance(scenario,str) or scenario not in CATALOG:return jsonify(error='Choose a weather type.'),400
        with lock:
            p=profile(owner);options=p.get('weather_options',{}).get(scenario,[])
            if len(options)<2:return jsonify(error='Select at least two looks for this weather in your wardrobe.'),400
            current=p.get('weather_outfits',{}).get(scenario)
            index=options.index(current) if current in options else -1
            p.setdefault('weather_outfits',{})[scenario]=options[(index+1)%len(options)]
            previous=profile(owner)
            save(owner,p)
            try:jid,reused=enqueue_weather(owner,scenario)
            except ValueError as e:
                save(owner,previous)
                return jsonify(error=str(e)),409
            remember(owner,jobs.approved(owner))
        return jsonify(id=jid,reused=reused),200 if reused else 202
    app.extensions['avatar_activate']=activate
    app.extensions['enqueue_weather_outfit']=enqueue_weather
