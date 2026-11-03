"""Timestamped past radar, with a bounded local tile proxy and attribution."""
import math,time,io,threading,re
from concurrent.futures import ThreadPoolExecutor
import requests
from PIL import Image
from flask import jsonify,session,send_file,abort
from fashn_transport import EncryptedDNSAdapter

def register_radar(app,profile):
    cache={};guard=threading.RLock()
    def get(url,kind='json'):
        with guard:
            hit=cache.get(url)
            if hit and time.time()-hit[0]<600:return hit[1]
        http=requests.Session()
        for host in ('api.rainviewer.com','tilecache.rainviewer.com','tile.openstreetmap.org'):
            http.mount('https://'+host+'/',EncryptedDNSAdapter(host))
        r=http.get(url,headers={'User-Agent':'WeatherAvatar-local-pilot/0.2 (local noncommercial weather preview)'},timeout=(8,20));r.raise_for_status()
        value=r.json() if kind=='json' else r.content
        with guard:
            if len(cache)>150:cache.clear()
            cache[url]=(time.time(),value)
        return value
    def frames():
        d=get('https://api.rainviewer.com/public/weather-maps.json')
        items=[x for x in d.get('radar',{}).get('past',[]) if isinstance(x.get('time'),int) and isinstance(x.get('path'),str) and re.fullmatch(r'/v2/radar/[A-Za-z0-9_-]{1,80}',x['path'])]
        if not items or time.time()-items[-1]['time']>3600:raise ValueError('Radar is outdated')
        return items[-4:]
    @app.get('/api/weather/radar')
    def radar():
        if not profile(session['owner']).get('location'):return jsonify(error='Choose a location'),400
        try:return jsonify(frames=[{'time':x['time'],'image':'/api/weather/radar/image/'+str(x['time'])} for x in frames()],attribution='Radar: RainViewer · Map: © OpenStreetMap contributors')
        except Exception:return jsonify(error='Radar is temporarily unavailable'),503
    @app.get('/api/weather/radar/image/<int:stamp>')
    def radar_image(stamp):
        loc=profile(session['owner']).get('location')
        if not loc:abort(404)
        try:
            frame=next((x for x in frames() if x['time']==stamp),None)
            if not frame:abort(404)
            radar_path=frame['path']
            z=7;n=2**z;lat=max(-85,min(85,loc['latitude']));lon=loc['longitude']
            xf=(lon+180)/360*n;yf=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
            left=math.floor(xf)-1;top=math.floor(yf)-1
            jobs=[(x,y,layer) for y in range(top,top+3) for x in range(left,left+3) for layer in (0,1)]
            def tile(job):
                x,y,layer=job;xw=x%n;yw=max(0,min(n-1,y))
                url=(f'https://tile.openstreetmap.org/{z}/{xw}/{yw}.png' if layer==0 else f'https://tilecache.rainviewer.com{radar_path}/256/{z}/{xw}/{yw}/2/1_1.png')
                return job,Image.open(io.BytesIO(get(url,'bytes'))).convert('RGBA')
            canvas=Image.new('RGBA',(768,768),'#e2e8e9');tiles={}
            with ThreadPoolExecutor(max_workers=8) as pool:
                for job,img in pool.map(tile,jobs):tiles[job]=img
            for layer in (0,1):
                for x,y,l in jobs:
                    if l==layer:canvas.alpha_composite(tiles[(x,y,l)],((x-left)*256,(y-top)*256))
            cx=int((xf-left)*256);cy=int((yf-top)*256)
            out=io.BytesIO();canvas.crop((cx-256,cy-256,cx+256,cy+256)).convert('RGB').save(out,'PNG');out.seek(0)
            return send_file(out,mimetype='image/png')
        except Exception:return jsonify(error='Radar image unavailable'),503
