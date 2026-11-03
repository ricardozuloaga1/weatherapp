import io
import os
import time
import unittest
from unittest.mock import patch
from PIL import Image
from pilot import create_app, estimated_cost, normalize_photo


def photo(size=(300, 400)):
    out = io.BytesIO()
    Image.new('RGB', size, '#aabbcc').save(out, format='PNG')
    return out.getvalue()


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def renderer(image, scenario, quality, **kwargs):
            self.calls.append((scenario, quality))
            return photo((1024, 1536)), {'input_tokens_details': {'text_tokens': 100, 'image_tokens': 200}, 'output_tokens': 300}
        self.app = create_app(renderer, store_path=':memory:')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.headers = {'X-CSRF-Token': session['csrf']}
        self.key = patch.dict(os.environ, {'OPENAI_API_KEY': 'test-placeholder'})
        self.key.start()

    def tearDown(self):
        self.app.extensions['pilot_pool'].shutdown(wait=True)
        self.app.extensions['pilot_store'].db.close()
        self.key.stop()

    def upload(self):
        return self.client.post('/api/pilot/photo', headers=self.headers, data={'photo': (io.BytesIO(photo()), 'face.png')})

    def run_images(self):
        return self.client.post('/api/pilot/runs', headers=self.headers, json={'scenario':'rain', 'qualities':['low','medium'], 'consent':True, 'request_id':'test-request-1'})

    def wait(self):
        for _ in range(100):
            jobs = self.client.get('/api/pilot').json['jobs']
            if all(j['status'] == 'done' for j in jobs):
                return jobs
            time.sleep(.01)
        self.fail('jobs did not finish')

    def test_complete_comparison_idempotency_ratings_export_delete(self):
        self.assertEqual(self.upload().status_code, 200)
        self.assertEqual(self.run_images().status_code, 202)
        jobs = self.wait()
        self.assertEqual(self.run_images().status_code, 200)
        self.assertEqual(len(self.calls), 2)
        self.assertAlmostEqual(jobs[0]['estimated_usd'], .0117)
        self.assertEqual(self.client.get('/api/pilot/images/'+jobs[0]['id']).status_code, 200)
        response = self.client.post('/api/pilot/ratings/'+jobs[0]['id'], headers=self.headers, json={'likeness':4,'outfit':5,'body':4,'framing':4,'garment':4,'boundary':4,'accepted':True})
        self.assertEqual(response.status_code, 200)
        exported = self.client.get('/api/pilot/export').json
        self.assertTrue(exported['jobs'][0]['rating']['accepted'])
        self.assertNotIn('image', exported['jobs'][0])
        self.assertEqual(self.client.delete('/api/pilot', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/api/pilot/images/'+jobs[0]['id']).status_code, 404)

    def test_private_session_and_csrf(self):
        self.upload(); self.run_images(); jobs=self.wait()
        other=self.app.test_client()
        self.assertEqual(other.get('/api/pilot/images/'+jobs[0]['id']).status_code,404)
        self.assertEqual(self.client.delete('/api/pilot').status_code,403)
        self.assertEqual(self.client.get('/api/pilot',environ_base={'REMOTE_ADDR':'192.168.1.2'}).status_code,403)

    def test_bad_image_and_unknown_cost(self):
        with self.assertRaises(ValueError):
            normalize_photo(b'not a photo')
        self.assertIsNone(estimated_cost({}))
        with Image.open(io.BytesIO(normalize_photo(photo()))) as image:
            self.assertEqual(image.format,'JPEG')
            self.assertFalse(image.getexif())

    def test_consent_and_input_validation(self):
        self.upload()
        for payload in [None, {'scenario':[]}, {'scenario':'sun','qualities':[{}]}, {'scenario':'sun','qualities':['low'],'request_id':'test-request-2'}]:
            response=self.client.post('/api/pilot/runs',headers=self.headers,json=payload)
            self.assertEqual(response.status_code,400)

    def test_failure_does_not_retry(self):
        def fail(*args, **kwargs):
            raise RuntimeError('Provider rejected request.')
        app=create_app(fail, store_path=':memory:'); client=app.test_client(); client.get('/')
        with client.session_transaction() as s: headers={'X-CSRF-Token':s['csrf']}
        client.post('/api/pilot/photo',headers=headers,data={'photo':(io.BytesIO(photo()),'face.png')})
        client.post('/api/pilot/runs',headers=headers,json={'scenario':'sun','qualities':['low'],'consent':True,'request_id':'failure-test'})
        for _ in range(100):
            jobs=client.get('/api/pilot').json['jobs']
            if jobs[0]['status']=='failed': break
            time.sleep(.01)
        self.assertEqual(jobs[0]['status'],'failed')
        self.assertNotIn('estimated_usd', jobs[0])
        app.extensions['pilot_pool'].shutdown(wait=True)
        app.extensions['pilot_store'].db.close()

if __name__ == '__main__': unittest.main()
