"""Live weather, persisted preferences and deterministic wardrobe selection."""
import math
import time
import threading
from datetime import datetime, timezone
import requests
from flask import request, session, jsonify
from fashn_transport import EncryptedDNSAdapter

# Curated options keep each outfit suitable for its weather band.
CATALOG = {
 'sun': {'label':'Warm & dry','slots':[['Ivory linen shirt','Cotton T-shirt'],['Olive linen trousers','Light cotton chinos'],['White sneakers','Canvas sneakers']]},
 'mild': {'label':'Cool or breezy','slots':[['Lightweight overshirt over a cotton tee','Light knit sweater'],['Cotton chinos','Straight-leg jeans'],['Low-top sneakers','Leather shoes']]},
 'rain': {'label':'Rain & wind','slots':[['Olive waterproof zip jacket without a hood','Navy waterproof rain shell'],['Charcoal trousers','Water-resistant chinos'],['Waterproof dark low-profile shoes','Waterproof ankle boots']]},
 'warmrain': {'label':'Warm & rainy','slots':[['Light breathable rain shell over a cotton tee','Light packable rain jacket over a linen shirt'],['Lightweight quick-dry trousers','Light water-resistant chinos'],['Light waterproof sneakers','Waterproof walking shoes']]},
 'cold': {'label':'Cold & dry','slots':[['Charcoal insulated jacket over a cream knit sweater','Insulated parka over a wool sweater'],['Wool trousers','Thermal-lined trousers'],['Dark insulated boots','Insulated walking boots']]},
 'coldrain': {'label':'Cold, rain or snow','slots':[['Waterproof insulated parka over a wool sweater and thermal layer','Waterproof winter jacket over a fleece and thermal layer'],['Water-resistant thermal-lined trousers','Insulated winter trousers'],['Waterproof insulated boots','Waterproof winter walking boots']]},
}
DEFAULT_PROMPTS = {
 'sun':'An ivory breathable linen short-sleeve shirt, tailored olive linen trousers, white low-top sneakers, no accessories covering the face.',
 'rain':'A fitted olive waterproof zip jacket without a hood, charcoal trousers and waterproof dark low-profile shoes.',
 'cold':'A fitted charcoal insulated hip-length jacket over a cream knit sweater, wool trousers, dark insulated boots and gloves, no scarf. Face unobstructed.',
}

def chosen(profile, scenario):
    return profile.get('wardrobe', {}).get(scenario, [0,0,0])

def signature(profile, scenario):
    selection=profile.get('weather_outfits',{}).get(scenario)
    if selection:return scenario+':photo:'+selection['kind']+':'+selection['id']
    return scenario + ':' + ','.join(map(str, chosen(profile, scenario)))

def outfit(profile, scenario):
    choices=chosen(profile,scenario)
    if choices==[0,0,0] and scenario in DEFAULT_PROMPTS:return DEFAULT_PROMPTS[scenario]
    return '. '.join(slot[i] for slot,i in zip(CATALOG[scenario]['slots'],choices))+'. Keep the face unobstructed.'

def recommend(data):
    current=data['current']; hourly=data['hourly']
    now=current['time']; times=hourly['time']
    indexes=[i for i,t in enumerate(times) if t>=now][:6]
    if not indexes: raise ValueError('Forecast is out of date')
    feels=[float(current['apparent_temperature'])]+[float(hourly['apparent_temperature'][i]) for i in indexes]
    low=min(feels); high=max(feels)
    wet=float(current['precipitation'])>0 or any(float(hourly['precipitation_probability'][i])>=50 or float(hourly['precipitation'][i])>=.2 for i in indexes)
    wind=max([float(current['wind_speed_10m'])]+[float(hourly['wind_speed_10m'][i]) for i in indexes])
    if not all(math.isfinite(v) for v in feels+[wind]):raise ValueError('Invalid forecast')
    scenario=('coldrain' if wet else 'cold') if low<=8 else ('warmrain' if low>=22 else 'rain') if wet else 'mild' if low<20 or wind>=25 else 'sun'
    reason=f'Feels like {round(low)}–{round(high)}°C over the next six hours. '+('Rain or snow is likely; choose water-resistant layers.' if wet else 'Dry conditions expected.')
    if wind>=25:reason+=' Wind calls for an extra layer.'
    return dict(scenario=scenario,reason=reason,temperature=current['temperature_2m'],feels_like=current['apparent_temperature'],wind=wind,wet=wet,observed_at=now,timezone=data.get('timezone'),fetched_at=time.time(),severe=low<-10 or wind>=60 or current.get('weather_code') in [95,96,99])

def conditions(code):
    if code == 0:return 'Clear'
    if code in (1,2):return 'Partly cloudy'
    if code == 3:return 'Overcast'
    if code in (45,48):return 'Fog'
    if code in (51,53,55,56,57):return 'Drizzle'
    if code in (61,63,65,66,67,80,81,82):return 'Rain'
    if code in (71,73,75,77,85,86):return 'Snow'
    if code in (95,96,99):return 'Thunderstorms'
    return 'Conditions unavailable'

def complete_forecast(data):
    result=recommend(data)
    c=data['current'];h=data['hourly'];d=data['daily']
    now=c['time']
    result.update(condition=conditions(c['weather_code']),code=c['weather_code'],is_day=bool(c.get('is_day')),current=c)
    indices=[i for i,t in enumerate(h['time']) if t>=now[:13]+':00'][:24]
    result['hours']=[{key:values[i] for key,values in h.items()} for i in indices]
    result['days']=[{key:values[i] for key,values in d.items()} for i in range(min(7,len(d['time'])))]
    m=data.get('minutely_15',{})
    mi=[i for i,t in enumerate(m.get('time',[])) if t>=now][:8]
    result['rain_intervals']=[{key:values[i] for key,values in m.items()} for i in mi]
    next_rain=next((x for x in result['hours'] if (x.get('precipitation_probability') or 0)>=50 or (x.get('precipitation') or 0)>=.2),None)
    result['rain_message']=('Precipitation now. Check the forecast before heading out.' if c['precipitation']>0 else ('Rain possible around '+next_rain['time'][11:16]+'.' if next_rain else 'No significant rain expected in the next 24 hours.'))
    return result

class WeatherClient:
    def __init__(self):
        self.http=requests.Session();self.cache={};self.lock=threading.Lock()
        for host in ['api.open-meteo.com','geocoding-api.open-meteo.com','air-quality-api.open-meteo.com']:
            self.http.mount('https://'+host+'/',EncryptedDNSAdapter(host))
    def search(self,name):
        r=self.http.get('https://geocoding-api.open-meteo.com/v1/search',params={'name':name,'count':5,'language':'en'},timeout=(8,15));r.raise_for_status()
        return [dict(label=', '.join(filter(None,[p['name'],p.get('admin1'),p.get('country')])),latitude=p['latitude'],longitude=p['longitude']) for p in r.json().get('results',[])]
    def air(self,loc):
        key=('air',loc['latitude'],loc['longitude']);cached=self.cache.get(key)
        if cached and time.time()-cached['fetched_at']<1800:return cached
        r=self.http.get('https://air-quality-api.open-meteo.com/v1/air-quality',params={**{k:loc[k] for k in ('latitude','longitude')},'current':'us_aqi,pm2_5,pm10','timezone':'auto'},timeout=(8,20));r.raise_for_status()
        result=dict(r.json()['current'],fetched_at=time.time());self.cache[key]=result;return result
    def forecast(self,loc):
        key=(loc['latitude'],loc['longitude']);cached=self.cache.get(key)
        if cached and time.time()-cached['fetched_at']<600:return cached
        params={'latitude':key[0],'longitude':key[1],'timezone':'auto','forecast_days':7,
                'current':'temperature_2m,apparent_temperature,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,surface_pressure,weather_code,is_day',
                'hourly':'is_day,temperature_2m,apparent_temperature,precipitation,precipitation_probability,wind_speed_10m,weather_code,visibility,uv_index',
                'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,sunrise,sunset,uv_index_max',
                'minutely_15':'precipitation','forecast_minutely_15':12}
        r=self.http.get('https://api.open-meteo.com/v1/forecast',params=params,timeout=(8,25));r.raise_for_status()
        data=r.json()
        observed=datetime.fromisoformat(data['current']['time']).replace(tzinfo=timezone.utc).timestamp()-data.get('utc_offset_seconds',0)
        if abs(time.time()-observed)>7200:raise ValueError('Forecast is out of date')
        result=complete_forecast(data);self.cache[key]=result;return result

def register_weather(app,store,lock):
    import json
    with store.db:store.db.execute('CREATE TABLE IF NOT EXISTS weather_profiles(owner TEXT PRIMARY KEY,body TEXT NOT NULL)')
    client=WeatherClient()
    def profile(owner):
        with lock:
            row=store.db.execute('SELECT body FROM weather_profiles WHERE owner=?',(owner,)).fetchone()
            return json.loads(row[0]) if row else {}
    def save(owner,data):
        with lock,store.db:store.db.execute('INSERT OR REPLACE INTO weather_profiles VALUES(?,?)',(owner,json.dumps(data)))
    @app.get('/api/weather/profile')
    def get_profile():return jsonify(profile=profile(session['owner']),catalog=CATALOG)
    @app.post('/api/weather/profile')
    def set_profile():
        body=request.get_json(silent=True)
        if not isinstance(body,dict):return jsonify(error='Invalid settings'),400
        p=profile(session['owner'])
        if 'location' in body:
            loc=body['location']
            try:
                lat,lon=loc['latitude'],loc['longitude']
                if type(lat) not in (float,int) or type(lon) not in (float,int) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError()
                label=loc['label']
                if not isinstance(label,str) or not 1<=len(label)<=150:raise ValueError()
                p['location']=dict(label=label,latitude=round(lat,2),longitude=round(lon,2))
            except (TypeError,KeyError,ValueError):return jsonify(error='Choose a valid location'),400
        if 'wardrobe' in body:
            w=body['wardrobe']
            if not isinstance(w,dict) or set(w)!=set(CATALOG):return jsonify(error='Choose clothes for every weather type'),400
            for k,v in w.items():
                if not isinstance(v,list) or len(v)!=3 or any(type(i)!=int or i not in (0,1) for i in v):return jsonify(error='Invalid wardrobe choice'),400
            p['wardrobe']=w;p['wardrobe_complete']=True
        if 'auto_generation' in body:
            if type(body['auto_generation']) is not bool:return jsonify(error='Invalid generation preference'),400
            p['auto_generation']=body['auto_generation']
        if body.get('welcome_seen') is True:p['welcome_seen']=True
        save(session['owner'],p);return jsonify(ok=True)
    @app.get('/api/weather/search')
    def search():
        name=request.args.get('q','').strip()
        if not 2<=len(name)<=80:return jsonify(error='Enter a city name'),400
        try:return jsonify(results=client.search(name))
        except Exception:return jsonify(error='City search is unavailable. Try again shortly.'),503
    @app.get('/api/weather/today')
    def today():
        p=profile(session['owner'])
        if not p.get('location'):return jsonify(error='Choose your location'),400
        try:
            result=client.forecast(p['location'])
            return jsonify(**result,location=p['location']['label'],wardrobe_signature=signature(p,result['scenario']))
        except Exception:return jsonify(error='Live weather is unavailable. Your saved looks are still available; try refreshing shortly.'),503
    @app.get('/api/weather/air')
    def air():
        loc=profile(session['owner']).get('location')
        if not loc:return jsonify(error='Choose your location'),400
        try:return jsonify(client.air(loc))
        except Exception:return jsonify(error='Air quality is temporarily unavailable'),503
    app.extensions['weather_profile']=profile
    app.extensions['weather_profile_save']=save
    app.extensions['weather_client']=client
    return profile
