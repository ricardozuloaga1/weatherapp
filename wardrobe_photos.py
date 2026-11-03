"""Owned garment photographs, exact saved-look details, and explicit try-on previews."""
import io,json,secrets,time
from PIL import Image,ImageOps,UnidentifiedImageError
from flask import request,session,jsonify,send_file,abort
from weather_live import CATALOG,signature

def register_garments(app,store,lock,jobs,profile):
    with lock,store.db:store.db.execute('CREATE TABLE IF NOT EXISTS garments(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,image BLOB NOT NULL,source TEXT NOT NULL,created REAL NOT NULL)')
    def owned(gid):
        with lock:return store.db.execute('SELECT name,category,image,source FROM garments WHERE id=? AND owner=?',(gid,session['owner'])).fetchone()
    @app.get('/api/garments')
    def library():
        with lock:
            return jsonify(items=[dict(id=r[0],name=r[1],category=r[2],source=r[3],image='/api/garments/'+r[0]+'/image') for r in store.db.execute('SELECT id,name,category,source FROM garments WHERE owner=? ORDER BY created',(session['owner'],))])
    @app.post('/api/garments')
    def garment_upload():
        f=request.files.get('photo');name=request.form.get('name','My garment').strip()[:80];category=request.form.get('category')
        if not f or category not in ('top','bottom','shoes','outfit'):return jsonify(error='Choose a garment photo and category'),400
        try:
            raw=f.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:raise ValueError()
            with Image.open(io.BytesIO(raw)) as original:
                if original.width*original.height>25000000 or min(original.size)<128:raise ValueError()
                im=ImageOps.exif_transpose(original).convert('RGB');im.thumbnail((1800,1800));out=io.BytesIO();im.save(out,'JPEG',quality=95)
        except (ValueError,UnidentifiedImageError,OSError):return jsonify(error='Choose a JPEG, PNG or WebP photo under 8 MB, at least 128 px wide'),400
        gid=secrets.token_hex(12)
        with lock,store.db:store.db.execute('INSERT INTO garments VALUES(?,?,?,?,?,?,?)',(gid,session['owner'],name or 'My garment',category,out.getvalue(),'Your uploaded photo',time.time()))
        return jsonify(id=gid),201
    @app.get('/api/garments/<gid>/image')
    def garment_image(gid):
        row=owned(gid)
        if not row:abort(404)
        return send_file(io.BytesIO(row[2]),mimetype='image/jpeg')
    @app.get('/api/fashn/images/<jid>/detail/<part>')
    def detail(jid,part):
        boxes={'outfit':(.12,.20,.88,.98),'top':(.28,.22,.73,.53),'bottom':(.31,.51,.70,.86),'shoes':(.30,.84,.71,.97)}
        raw=jobs.image(session['owner'],jid)
        if part not in boxes or not raw:abort(404)
        with Image.open(io.BytesIO(raw)) as im:
            b=boxes[part];im=im.crop((int(b[0]*im.width),int(b[1]*im.height),int(b[2]*im.width),int(b[3]*im.height)));im.thumbnail((600,600));out=io.BytesIO();im.convert('RGB').save(out,'JPEG',quality=92)
        out.seek(0);return send_file(out,mimetype='image/jpeg')
    @app.post('/api/garments/try-on')
    def tryon():
        b=request.get_json(silent=True) or {};gid=b.get('garment_id');parent=b.get('look_id');scenario=b.get('scenario')
        if b.get('consent') is not True:return jsonify(error='Confirm sending the garment and avatar to FASHN'),400
        row=owned(gid);base=jobs.approved(session['owner']);source=jobs.image(session['owner'],parent)
        parentjob=next((j for j in jobs.public_jobs(session['owner']) if j['id']==parent),None)
        if not row or not base or not source or not parentjob or scenario not in CATALOG:return jsonify(error='Choose an owned garment, saved look and weather type'),400
        if parent!=base and parentjob.get('avatar_id')!=base:return jsonify(error='Switch to this look’s avatar profile first'),400
        if parentjob.get('preview') and not parentjob.get('accepted'):return jsonify(error='Save this preview before using it for another change'),400
        garment_ids=dict(parentjob.get('garment_ids',{}));garment_ids[row[1]]=gid
        try:
            jid,reused=jobs.enqueue(session['owner'],source,'outfit',scenario,base,'Garment photograph '+gid,signature(profile(session['owner']),scenario),product=row[2],garment_ids=garment_ids,parent_look_id=parent)
            return jsonify(id=jid,reused=reused),200 if reused else 202
        except ValueError as e:return jsonify(error=str(e)),409
    @app.post('/api/garments/accept')
    def accept():
        b=request.get_json(silent=True) or {};jid=b.get('id')
        with lock,store.db:
            row=store.db.execute("SELECT metadata FROM fashn_jobs WHERE id=? AND owner=? AND status='done' AND deleted=0",(jid,session['owner'])).fetchone()
            if not row:abort(404)
            m=json.loads(row[0])
            if m.get('kind')!='outfit':return jsonify(error='Choose an outfit'),400
            if m.get('avatar_id')!=jobs.approved(session['owner']):return jsonify(error='Switch to this look’s avatar profile first'),400
            m['accepted']=True;store.db.execute('UPDATE fashn_jobs SET metadata=? WHERE id=?',(json.dumps(m),jid))
            p=profile(session['owner']);p.setdefault('preferred_looks',{})[m['scenario']]=jid
            app.extensions['weather_profile_save'](session['owner'],p)
        return jsonify(ok=True)
