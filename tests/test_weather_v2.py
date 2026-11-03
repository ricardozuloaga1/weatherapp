import io,json,unittest
from unittest.mock import Mock,patch
from PIL import Image
from pilot import create_app
from weather_live import complete_forecast
from test_weather_live import forecast
from test_fashn import image,Client

class FullWeatherTests(unittest.TestCase):
    def test_full_forecast_preserves_provider_values_and_nulls(self):
        d=forecast();d['current'].update(is_day=1,relative_humidity_2m=61)
        d['hourly'].update(temperature_2m=[24]*7,weather_code=[2]*7,visibility=[None]*7,uv_index=[1.5]*7)
        d['daily']={'time':['2026-11-02','2026-11-03'],'temperature_2m_max':[25,26],'temperature_2m_min':[15,16]}
        d['minutely_15']={'time':['2026-11-02T12:15','2026-11-02T12:30'],'precipitation':[0,.2]}
        out=complete_forecast(d)
        self.assertEqual(len(out['days']),2);self.assertIsNone(out['hours'][0]['visibility'])
        self.assertEqual(out['rain_intervals'][1]['precipitation'],.2)
        self.assertEqual(out['current']['relative_humidity_2m'],61)

class PhotoWardrobeTests(unittest.TestCase):
    def setUp(self):
        self.client=Client();self.client.submit_tryon=Mock(return_value='tryon-1')
        self.app=create_app(store_path=':memory:',fashn_client=self.client,fashn_autostart=False)
        self.c=self.app.test_client();self.c.get('/')
        with self.c.session_transaction() as s:self.owner=s['owner'];self.h={'X-CSRF-Token':s['csrf']}
        self.jobs=self.app.extensions['fashn'];self.base=self.jobs.import_studio(self.owner,image());self.jobs.approve(self.owner,self.base)
    def tearDown(self):self.app.extensions['pilot_pool'].shutdown();self.app.extensions['pilot_store'].db.close()
    def upload(self):return self.c.post('/api/garments',headers=self.h,data={'name':'Real shirt','category':'top','photo':(io.BytesIO(image()),'shirt.png')}).json['id']
    def test_photos_are_private_and_require_csrf(self):
        self.assertEqual(self.c.post('/api/garments').status_code,403)
        gid=self.upload();self.assertEqual(self.c.get('/api/garments/'+gid+'/image').status_code,200)
        other=self.app.test_client();other.get('/')
        self.assertEqual(other.get('/api/garments').json['items'],[])
        self.assertEqual(other.get('/api/garments/'+gid+'/image').status_code,404)
        self.assertEqual(other.get('/api/fashn/images/'+self.base+'/detail/top').status_code,404)
    def test_tryon_deduplicates_and_requires_explicit_acceptance(self):
        gid=self.upload();body={'garment_id':gid,'look_id':self.base,'scenario':'mild','consent':True}
        a=self.c.post('/api/garments/try-on',headers=self.h,json=body);b=self.c.post('/api/garments/try-on',headers=self.h,json=body)
        self.assertEqual(a.status_code,202);self.assertEqual(a.json['id'],b.json['id'])
        self.jobs.tick();self.jobs.tick();self.assertEqual(self.client.submit_tryon.call_count,1)
        j=next(x for x in self.jobs.public_jobs(self.owner) if x['id']==a.json['id'])
        self.assertEqual(j['model'],'tryon-max');self.assertFalse(j['accepted']);self.assertEqual(j['actual_credits'],3)
        self.assertEqual(self.jobs.approved(self.owner),self.base)
        self.assertEqual(self.c.post('/api/garments/accept',headers=self.h,json={'id':a.json['id']}).status_code,200)
        self.assertEqual(self.app.extensions['weather_profile'](self.owner)['preferred_looks']['mild'],a.json['id'])
        self.assertEqual(self.jobs.approved(self.owner),self.base)
        self.c.delete('/api/pilot',headers=self.h);self.assertEqual(self.c.get('/api/garments').json['items'],[])

class RadarTests(unittest.TestCase):
    def test_current_opaque_frame_paths_are_accepted(self):
        import time
        app=create_app(store_path=':memory:',fashn_autostart=False);c=app.test_client();c.get('/')
        with c.session_transaction() as s:owner=s['owner']
        app.extensions['weather_profile_save'](owner,{'location':{'latitude':40.71,'longitude':-74.01,'label':'NYC'}})
        response=Mock();response.json.return_value={'radar':{'past':[{'time':int(time.time()),'path':'/v2/radar/1482fad9815f'}]}}
        with patch('weather_radar.requests.Session.get',return_value=response):
            r=c.get('/api/weather/radar');self.assertEqual(r.status_code,200);self.assertEqual(len(r.json['frames']),1)
        app.extensions['pilot_pool'].shutdown();app.extensions['pilot_store'].db.close()
