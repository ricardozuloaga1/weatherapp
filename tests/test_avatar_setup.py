import io,unittest
from unittest.mock import Mock
from PIL import Image
from pilot import create_app
from weather_live import CATALOG,signature
from test_fashn import Client,image

class SetupFlowTests(unittest.TestCase):
    def setUp(self):
        self.provider=Client();self.provider.submit_tryon=Mock(return_value='photo-outfit-1')
        self.app=create_app(store_path=':memory:',fashn_client=self.provider,fashn_autostart=False)
        self.c=self.app.test_client();self.c.get('/')
        with self.c.session_transaction() as s:self.owner=s['owner'];self.h={'X-CSRF-Token':s['csrf']}
        self.jobs=self.app.extensions['fashn'];self.jobs.reviewer=Mock();self.jobs.reviewer.review.return_value={'face_and_frame_ok':True,'clothing_ok':True};self.a=self.jobs.import_studio(self.owner,image());self.jobs.approve(self.owner,self.a)
        self.look=self.jobs.import_studio(self.owner,image(),'outfit','sun',self.a)
        b=io.BytesIO();Image.new('RGB',(640,960),'blue').save(b,'PNG');self.b=self.jobs.import_studio(self.owner,b.getvalue())
        self.profile=self.app.extensions['weather_profile'];self.save=self.app.extensions['weather_profile_save']
        self.save(self.owner,{'location':{'label':'NYC','latitude':40.71,'longitude':-74.01},'wardrobe_complete':True,'preferred_looks':{'sun':self.look},'auto_generation':False})
    def tearDown(self):self.app.extensions['pilot_pool'].shutdown();self.app.extensions['pilot_store'].db.close()
    def post(self,url,body):return self.c.post(url,headers=self.h,json=body)
    def test_photo_approval_wardrobe_render_reuse_and_restore(self):
        self.assertEqual(self.post('/api/setup/approve',{'id':self.b,'approved':True,'name':'New profile'}).status_code,200)
        self.assertEqual(self.jobs.approved(self.owner),self.b);self.assertNotIn('wardrobe_complete',self.profile(self.owner))
        self.assertEqual(self.profile(self.owner)['location']['label'],'NYC')
        choices={k:{'kind':'look','id':self.look} for k in CATALOG}
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,200)
        self.assertEqual(self.profile(self.owner)['weather_outfits'],choices)
        req={'scenario':'sun','consent':True};r=self.post('/api/fashn/dress',req)
        self.assertEqual(r.status_code,202);jid=r.json['id']
        self.jobs.tick();self.jobs.tick();self.jobs.tick()
        j=next(j for j in self.jobs.public_jobs(self.owner) if j['id']==jid)
        self.assertEqual(j['avatar_id'],self.b);self.assertTrue(j['full_outfit']);self.assertTrue(j['accepted'])
        self.assertEqual(j['wardrobe_signature'],signature(self.profile(self.owner),'sun'))
        self.assertEqual(self.post('/api/fashn/dress',req).json['id'],jid);self.assertEqual(self.provider.submit_tryon.call_count,1)
        self.assertEqual(self.post('/api/setup/switch',{'id':self.a}).status_code,200)
        self.assertEqual(self.profile(self.owner)['preferred_looks']['sun'],self.look);self.assertNotIn('weather_outfits',self.profile(self.owner))
        self.assertEqual(self.post('/api/setup/switch',{'id':self.b}).status_code,200)
        self.assertEqual(self.profile(self.owner)['weather_outfits'],choices)
        self.assertIsNotNone(self.jobs.image(self.owner,self.a));self.assertIsNotNone(self.jobs.image(self.owner,self.look))
    def test_incomplete_or_foreign_wardrobe_and_unapproved_switch_rejected(self):
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':{}}).status_code,400)
        choices={k:{'kind':'look','id':'someone-elses-look'} for k in CATALOG}
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,400)
        self.assertEqual(self.post('/api/setup/switch',{'id':self.b}).status_code,400)
        other=self.app.test_client();other.get('/')
        with other.session_transaction() as s:h={'X-CSRF-Token':s['csrf']}
        self.assertEqual(other.post('/api/setup/approve',headers=h,json={'id':self.b,'approved':True}).status_code,400)
        self.assertTrue(all(c['kind']=='starter' for c in other.get('/api/setup').json['choices']))
        self.assertEqual(self.c.post('/api/setup/approve',json={'id':self.b,'approved':True}).status_code,403)
    def test_uploaded_complete_outfit_is_selectable(self):
        r=self.c.post('/api/garments',headers=self.h,data={'name':'My winter outfit','category':'outfit','photo':(io.BytesIO(image()),'outfit.png')})
        self.assertEqual(r.status_code,201)
        choice=next(x for x in self.c.get('/api/setup').json['choices'] if x['id']==r.json['id'])
        self.assertEqual(choice['kind'],'garment')
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':{k:{'id':choice['id'],'kind':'garment'} for k in CATALOG}}).status_code,200)

    def test_starter_outfits_available_to_new_users_and_validated(self):
        starter=next(c for c in self.c.get('/api/setup').json['choices'] if c['kind']=='starter')
        with self.c.get(starter['image']) as response:self.assertEqual(response.status_code,200)
        choices={k:{'kind':'starter','id':starter['id']} for k in CATALOG}
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,200)
        self.assertEqual(self.post('/api/fashn/dress',{'scenario':'sun','consent':True}).status_code,202)
        choices['sun']['id']='../../private'
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,400)

    def test_existing_look_on_same_avatar_reused_without_charge(self):
        choices={k:{'kind':'look','id':self.look} for k in CATALOG}
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,200)
        result=self.post('/api/fashn/dress',{'scenario':'cold','consent':True})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json,{'id':self.look,'reused':True})
        self.provider.submit_tryon.assert_not_called()

    def test_multiple_choices_persist_cycle_and_restore(self):
        second=self.jobs.import_studio(self.owner,image(),'outfit','rain',self.a)
        first={'kind':'look','id':self.look};other={'kind':'look','id':second}
        choices={k:[first,other,first] for k in CATALOG}
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,200)
        self.assertEqual(self.profile(self.owner)['weather_options']['sun'],[first,other])
        self.assertEqual(self.post('/api/setup/another',{'scenario':'sun','consent':True}).json,{'id':second,'reused':True})
        self.assertEqual(self.profile(self.owner)['weather_outfits']['sun'],other)
        self.post('/api/setup/approve',{'id':self.b,'approved':True})
        self.assertNotIn('weather_options',self.profile(self.owner))
        self.post('/api/setup/switch',{'id':self.a})
        self.assertEqual(self.profile(self.owner)['weather_options']['sun'],[first,other])
        self.assertEqual(self.profile(self.owner)['weather_outfits']['sun'],other)
        self.assertEqual(self.post('/api/setup/another',{'scenario':'sun','consent':True}).json['id'],self.look)
        self.provider.submit_tryon.assert_not_called()

    def test_multiple_choices_validation_and_failed_rotation_preserves_current(self):
        first={'kind':'look','id':self.look};other={'kind':'starter','id':'linen'}
        choices={k:[first,other] for k in CATALOG}
        self.post('/api/setup/wardrobe',{'choices':choices})
        self.jobs.user_limit=0
        self.assertEqual(self.post('/api/setup/another',{'scenario':'sun','consent':True}).status_code,409)
        self.assertEqual(self.profile(self.owner)['weather_outfits']['sun'],first)
        choices['sun']=[]
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,400)
        choices['sun']=[{'kind':'look','id':'foreign'}]
        self.assertEqual(self.post('/api/setup/wardrobe',{'choices':choices}).status_code,400)
        self.assertEqual(self.post('/api/setup/another',{'scenario':'sun'}).status_code,400)

    def test_checked_look_matches_identical_reference_across_weather(self):
        choices={k:{'kind':'starter','id':'parka'} for k in CATALOG}
        self.post('/api/setup/wardrobe',{'choices':choices})
        r=self.post('/api/fashn/dress',{'scenario':'cold','consent':True});jid=r.json['id']
        pending=self.c.get('/api/fashn').json['weather_pending']
        self.assertEqual(pending['rain'],jid)
        self.jobs.tick();self.jobs.tick();self.jobs.tick()
        state=self.c.get('/api/fashn').json
        self.assertEqual(state['weather_matches']['rain'],jid)
        self.assertEqual(state['weather_matches']['cold'],jid)
        self.assertEqual(self.post('/api/fashn/dress',{'scenario':'rain','consent':True}).json,{'id':jid,'reused':True})
        self.assertEqual(self.provider.submit_tryon.call_count,1)
