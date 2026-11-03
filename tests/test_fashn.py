import base64
import io
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch, Mock

import requests
from PIL import Image
from fashn import FashnJobs, FashnClient, SETTINGS
from pilot import create_app


def image():
    buf=io.BytesIO(); Image.new('RGB',(640,960)).save(buf,'PNG'); return buf.getvalue()


class Client:
    ready=True
    def __init__(self): self.submits=0; self.polls=0
    def submit(self, source, prompt): self.submits+=1; return 'prediction-1'
    def poll(self, prediction):
        self.polls+=1
        return {'status':'completed','output':['data:image/png;base64,'+base64.b64encode(image()).decode()]},3


class FashnTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.client=Client()
        self.jobs=FashnJobs(self.db,threading.RLock(),self.client,autostart=False,user_limit=6,global_limit=9)
    def tearDown(self): self.db.close()
    def base(self): return self.jobs.enqueue('owner',image(),'base')[0]
    def complete(self): self.jobs.tick();self.jobs.tick()

    def test_deduplication_credits_and_base_input(self):
        job=self.base();self.assertEqual(job,self.base());self.complete()
        self.assertEqual(self.client.submits,1)
        self.assertEqual(self.jobs.public_jobs('owner')[0]['actual_credits'],3)
        self.jobs.approve('owner',job)
        source=self.jobs.image('owner',job)
        self.jobs.enqueue('owner',source,'outfit','sun',job,'linen shirt')
        self.assertRaises(ValueError,self.jobs.enqueue,'owner',source,'outfit','rain',job,'jacket')
        self.complete();self.jobs.tick()
        self.assertEqual(self.db.execute('SELECT SUM(charge) FROM fashn_jobs').fetchone()[0],6)
        self.assertEqual(self.jobs.public_jobs('owner')[0]['dimensions'],[640,960])

    def test_restart_polls_known_id_without_submit(self):
        job=self.base();self.jobs.tick()
        restored=FashnJobs(self.db,threading.RLock(),self.client,autostart=False)
        restored.tick()
        self.assertEqual(self.client.submits,1)
        self.assertEqual(restored.public_jobs('owner')[0]['status'],'done')
        self.assertIsNotNone(restored.image('owner',job))

    def test_timeout_and_interrupted_submission_never_resubmit(self):
        self.client.submit=Mock(side_effect=requests.Timeout())
        job=self.base();self.jobs.tick();self.jobs.tick()
        self.assertEqual(self.jobs.public_jobs('owner')[0]['status'],'unknown')
        self.assertEqual(self.client.submit.call_count,1)
        self.assertEqual(self.base(),job)
        self.assertEqual(self.jobs.public_jobs('owner')[0]['credits_reserved_or_used'],3)
        self.db.execute("UPDATE fashn_jobs SET status='submitting'")
        restored=FashnJobs(self.db,threading.RLock(),self.client,autostart=False)
        self.assertEqual(restored.public_jobs('owner')[0]['status'],'unknown')

    def test_deleted_inflight_result_not_resurrected_and_budget_retained(self):
        job=self.base();self.jobs.tick();self.jobs.delete('owner');self.jobs.tick()
        self.assertIsNone(self.jobs.image('owner',job));self.assertEqual(self.jobs.public_jobs('owner'),[])
        self.assertEqual(self.db.execute('SELECT charge FROM fashn_jobs').fetchone()[0],3)

    def test_failure_releases_reservation_expired_result_does_not(self):
        self.base();self.jobs.tick();self.client.poll=lambda p:({'status':'failed'},None);self.jobs.tick()
        self.assertEqual(self.db.execute('SELECT charge FROM fashn_jobs').fetchone()[0],0)
        self.jobs.enqueue('other',image(),'base');self.jobs.tick()
        self.client.poll=lambda p:({'status':'completed','output':['<base64>_expired']},3);self.jobs.tick()
        self.assertEqual(self.jobs.public_jobs('other')[0]['status'],'unavailable')
        self.assertEqual(self.jobs.public_jobs('other')[0]['credits_reserved_or_used'],3)

    def test_simultaneous_duplicate_reserves_once(self):
        threads=[threading.Thread(target=self.base) for _ in range(6)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(self.db.execute('SELECT COUNT(*),SUM(charge) FROM fashn_jobs').fetchone(),(1,3))

    def test_studio_import_is_private_idempotent_and_free(self):
        base=self.jobs.import_studio('owner',image())
        self.assertEqual(base,self.jobs.import_studio('owner',image()))
        self.jobs.approve('owner',base)
        look=self.jobs.import_studio('owner',image(),'outfit','sun',base)
        self.assertEqual(self.jobs.approved('owner'),base)
        self.assertIsNone(self.jobs.image('other',look))
        self.assertEqual(self.db.execute('SELECT SUM(charge) FROM fashn_jobs').fetchone()[0],0)
        self.assertEqual(self.client.submits,0)
        self.assertEqual(self.jobs.public_jobs('owner')[0]['provenance'],'studio-original-export')

    def test_adapter_contract(self):
        response=Mock(status_code=200);response.json.return_value={'id':'test-id'}
        with patch.dict('os.environ',{'FASHN_API_KEY':'mock-only'}),patch('fashn.requests.post',return_value=response) as post:
            self.assertEqual(FashnClient().submit(image(),'prompt'),'test-id')
            payload=post.call_args.kwargs['json']
            self.assertEqual(payload['model_name'],'edit')
            self.assertEqual({k:payload['inputs'][k] for k in SETTINGS},SETTINGS)
            self.assertNotIn('mask',payload['inputs'])

    def test_routes_owner_csrf_and_saved_selfie(self):
        app=create_app(store_path=':memory:',fashn_client=self.client,fashn_autostart=False)
        c=app.test_client();c.get('/')
        with c.session_transaction() as s: headers={'X-CSRF-Token':s['csrf']}
        c.post('/api/pilot/photo',headers=headers,data={'photo':(io.BytesIO(image()),'selfie.png')})
        self.assertEqual(c.post('/api/fashn/base',json={'consent':True}).status_code,403)
        r=c.post('/api/fashn/base',headers=headers,json={'consent':True});self.assertEqual(r.status_code,202)
        jobs=app.extensions['fashn'];jobs.tick();jobs.tick()
        id_=r.json['id'];self.assertEqual(c.get('/api/fashn/images/'+id_).status_code,200)
        other=app.test_client();self.assertEqual(other.get('/api/fashn/images/'+id_).status_code,404)
        self.assertNotIn('data:image',c.get('/api/fashn').text)
        self.assertEqual(c.post('/api/fashn/approve',headers=headers,json={'approved':True,'job_id':id_}).status_code,200)
        c.delete('/api/pilot',headers=headers)
        self.assertEqual(c.get('/api/fashn/images/'+id_).status_code,404)
        app.extensions['pilot_pool'].shutdown();app.extensions['pilot_store'].db.close()

if __name__=='__main__':unittest.main()
