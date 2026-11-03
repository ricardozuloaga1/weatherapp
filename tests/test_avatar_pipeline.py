import io
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from avatar_pipeline import cache_key, edit_mask, head_masks, png, preserve_head, valid_box
from pilot import create_app, generate
from pilot_store import PilotStore


class PipelineTests(unittest.TestCase):
    def test_protection_and_mask(self):
        reference = png(Image.new('RGB', (1024, 1536), 'red'))
        generated = png(Image.new('RGB', (1024, 1536), 'blue'))
        box = [.35, .04, .3, .22]
        output, checks = preserve_head(reference, generated, box)
        self.assertTrue(checks['protected_core_unchanged'])
        image = Image.open(io.BytesIO(output))
        self.assertEqual(image.getpixel((512, 200)), (255, 0, 0))
        self.assertEqual(image.getpixel((512, 1200)), (0, 0, 255))
        mask = Image.open(io.BytesIO(edit_mask(reference, box)))
        self.assertEqual(mask.getpixel((512, 200))[3], 255)
        self.assertEqual(mask.getpixel((512, 1200))[3], 0)
        with self.assertRaises(ValueError):
            preserve_head(reference, png(Image.new('RGB', (256, 256))), box)
        self.assertFalse(valid_box([.8, .1, .5, .2]))
        self.assertFalse(valid_box([float('nan'), .1, .2, .2]))

    def test_provider_adapter_sends_png_mask_and_fixed_settings(self):
        import base64
        reference = png(Image.new('RGB', (1024, 1536), 'gray'))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-only'}), patch('pilot.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'data': [{'b64_json': base64.b64encode(reference).decode()}], 'usage': {}}
            result, _ = generate(reference, 'rain', 'medium', mode='protected', head_box=[.35,.04,.3,.22])
            self.assertEqual(result, reference)
            kwargs = post.call_args.kwargs
            self.assertEqual(kwargs['data']['size'], '1024x1536')
            self.assertEqual(kwargs['data']['quality'], 'medium')
            self.assertEqual(kwargs['data']['input_fidelity'], 'high')
            self.assertEqual(kwargs['files']['mask'][2], 'image/png')
            self.assertEqual(Image.open(io.BytesIO(kwargs['files']['mask'][1])).size, (1024,1536))
            self.assertEqual(post.call_count, 1)

    def test_cache_keys(self):
        key = cache_key('avatar1', 'sun', 'protected', 'medium')
        self.assertEqual(key, cache_key('avatar1', 'sun', 'protected', 'medium'))
        for other in [('avatar2','sun','protected','medium'), ('avatar1','rain','protected','medium'), ('avatar1','sun','avatar','medium'), ('avatar1','sun','protected','high')]:
            self.assertNotEqual(key, cache_key(*other))

    def test_durable_versions_cache_comparison_and_recovery(self):
        calls = []
        def renderer(photo, scenario, quality, **kwargs):
            calls.append(kwargs['mode'])
            return png(Image.new('RGB', (1024,1536), '#c1bca7')), {'input_tokens_details':{'text_tokens':100,'image_tokens':200}, 'output_tokens':300}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'OPENAI_API_KEY':'test-only'}):
            path = Path(directory) / 'pilot.sqlite3'
            app = create_app(renderer, path); app.config['TESTING'] = True
            client = app.test_client(); client.get('/')
            with client.session_transaction() as sess:
                headers={'X-CSRF-Token':sess['csrf']}; owner=sess['owner']; cookie=dict(sess)
            def post(url, data):
                return client.post('/api/pilot/'+url, headers=headers, json=data)
            def wait():
                for _ in range(200):
                    state=client.get('/api/pilot').json
                    if not any(j['status'] in {'queued','generating'} for j in state['jobs']): return state
                    time.sleep(.01)
                self.fail('queue did not finish')
            image=png(Image.new('RGB',(300,400),'gray'))
            client.post('/api/pilot/photo',headers=headers,data={'photo':(io.BytesIO(image),'selfie.png')})
            request={'consent':True,'request_id':'reference-1','quality':'low','preferences':'Broad shoulders'}
            self.assertEqual(post('avatar',request).status_code,202)
            candidate=wait()['jobs'][0]
            self.assertEqual(candidate['status'],'done')
            self.assertIsNone(client.get('/api/pilot').json['active_avatar'])
            approval={'job_id':candidate['id'],'head_box':[.35,.04,.3,.22],'approved':True}
            avatar=post('approve',approval).json['avatar']
            self.assertEqual(post('approve',approval).json['avatar']['id'],avatar['id'])
            run={'scenario':'rain','qualities':['low'],'modes':['selfie','avatar','protected'],'consent':True,'request_id':'compare-1','avatar_id':avatar['id']}
            self.assertEqual(post('runs',run).status_code,202)
            state=wait(); self.assertEqual(len(state['jobs']),4)
            protected=state['jobs'][-1]
            self.assertTrue(protected['checks']['protected_core_unchanged'])
            run['request_id']='compare-2'
            self.assertEqual(post('runs',run).json['reused'],3)
            self.assertEqual(len(calls),4)
            rating={k:4 for k in ['likeness','body','framing','garment','outfit','boundary']}; rating['accepted']=False
            self.assertEqual(post('ratings/'+protected['id'],rating).status_code,200)
            run['request_id']='compare-3'
            self.assertEqual(post('runs',run).json['generated'],1)
            wait(); self.assertEqual(len(calls),5)
            # Persistence retains owner, immutable versions, images and the spend allowance.
            restarted=create_app(renderer,path); resumed=restarted.test_client()
            with resumed.session_transaction() as sess: sess.update(cookie)
            recovered=resumed.get('/api/pilot').json
            self.assertEqual(len(recovered['jobs']),5)
            self.assertEqual(recovered['active_avatar'],avatar['id'])
            self.assertEqual(recovered['remaining'],19)
            self.assertEqual(resumed.get('/api/pilot/images/'+candidate['id']).status_code,200)
            self.assertEqual(os.stat(path).st_mode & 0o777,0o600)
            # Deliberate new version: same selfie with corrected preferences, no silent replacement.
            request.update(request_id='reference-2',preferences='Slender build')
            post('avatar',request); second=wait()['jobs'][-1]
            self.assertEqual(client.get('/api/pilot').json['active_avatar'],avatar['id'])
            approval['job_id']=second['id']; new=post('approve',approval).json['avatar']
            self.assertEqual(new['version'],2)
            self.assertNotEqual(new['id'],avatar['id'])
            for application in (app, restarted):
                application.extensions['pilot_pool'].shutdown(wait=True)
                application.extensions['pilot_store'].db.close()

    def test_interrupted_jobs_are_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'store.sqlite3'; store=PilotStore(path)
            store.save('owner',{'photo':b'photo','jobs':[{'id':'job','status':'generating'}], 'avatars':[]},submitted=1)
            recovered_store=PilotStore(path)
            record=recovered_store.load()['owner']
            recovered_store.db.close()
            self.assertEqual(record['jobs'][0]['status'],'interrupted')
            self.assertIn('Billing may have occurred',record['jobs'][0]['error'])
            store.delete('owner')
            self.assertEqual(store.load(),{})
            self.assertEqual(store.count(),1)
            store.db.close()

if __name__ == '__main__': unittest.main()
