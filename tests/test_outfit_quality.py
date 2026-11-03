import unittest,sqlite3,threading,json
from unittest.mock import Mock
from fashn import FashnJobs
from test_fashn import Client,image

class ReviewedOutfitTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.client=Client();self.client.submit_tryon=Mock(return_value='prediction')
        self.jobs=FashnJobs(self.db,threading.RLock(),self.client,False,100,100)
        self.base=self.jobs.import_studio('owner',image())
        self.jobs.reviewer=Mock()
        self.good={'face_and_frame_ok':True,'clothing_ok':True,'crop':[0,0,1,1],'reason':'match','repair_instruction':''}
        self.bad={**self.good,'clothing_ok':False,'repair_instruction':'Replace old trousers and shoes','crop':[0,.4,1,1]}
    def tearDown(self):self.db.close()
    def enqueue(self,scenario='cold',owner='owner',base=None):
        return self.jobs.enqueue(owner,image(),'outfit',scenario,base or self.base,'full outfit',product=image(),full_outfit=True)
    def run_all(self):
        for _ in range(15):
            if not self.jobs.tick():break
    def result(self):return self.jobs.public_jobs('owner')[-1]
    def test_repair_then_accept_reuse_across_weather(self):
        self.jobs.reviewer.review.side_effect=[self.bad,self.good]
        jid,_=self.enqueue();self.run_all();j=self.result()
        self.assertEqual(j['status'],'done');self.assertTrue(j['accepted']);self.assertEqual(j['repair_count'],1)
        self.assertEqual(j['credits_reserved_or_used'],6);self.assertEqual(self.client.submit_tryon.call_count,2)
        self.assertIn('Replace old trousers',self.client.submit_tryon.call_args.kwargs['prompt'])
        self.assertEqual(self.enqueue('rain'),(jid,True))
        self.assertFalse(self.enqueue('cold',owner='other')[1])
        self.assertFalse(self.enqueue('cold',base='other-avatar')[1])
    def test_two_repairs_max_never_auto_accept_failure(self):
        self.jobs.reviewer.review.return_value=self.bad;self.enqueue();self.run_all();j=self.result()
        self.assertEqual(j['repair_count'],2);self.assertFalse(j['accepted']);self.assertTrue(j['preview'])
        self.assertEqual(j['credits_reserved_or_used'],9);self.assertEqual(self.client.submit_tryon.call_count,3)
    def test_identity_failure_does_not_spend_on_clothing(self):
        self.jobs.reviewer.review.return_value={**self.bad,'face_and_frame_ok':False}
        self.enqueue();self.run_all();self.assertFalse(self.result()['accepted']);self.assertEqual(self.client.submit_tryon.call_count,1)
    def test_checker_failure_keeps_preview_and_budget_blocks_repairs(self):
        self.jobs.reviewer.review.side_effect=RuntimeError('provider unavailable');self.enqueue();self.run_all()
        self.assertFalse(self.result()['accepted']);self.assertEqual(self.result()['credits_reserved_or_used'],3)
        self.assertIsNotNone(self.jobs.image('owner',self.result()['id']))
    def test_budget_exhaustion_preserves_paid_result(self):
        self.jobs.user_limit=3;self.jobs.reviewer.review.return_value=self.bad;self.enqueue();self.run_all()
        self.assertEqual(self.client.submit_tryon.call_count,1);self.assertFalse(self.result()['accepted'])
    def test_restart_review_keeps_reference_and_no_generation_duplicate(self):
        jid,_=self.enqueue();self.jobs.tick();self.jobs.tick()
        self.assertEqual(self.result()['status'],'reviewing')
        restored=FashnJobs(self.db,threading.RLock(),self.client,False,100,100)
        restored.reviewer=Mock();restored.reviewer.review.return_value=self.good;restored.tick()
        self.assertEqual(self.client.submit_tryon.call_count,1);self.assertTrue(self.result()['accepted'])
    def test_failed_repair_retains_first_pass_charge(self):
        self.jobs.reviewer.review.return_value=self.bad;self.enqueue()
        self.jobs.tick();self.jobs.tick();self.jobs.tick();self.jobs.tick()
        self.client.poll=lambda _:({'status':'failed'},None);self.jobs.tick()
        self.assertEqual(self.result()['credits_reserved_or_used'],3);self.assertFalse(self.result()['accepted'])
    def test_external_benchmark_spend_counts_toward_limit(self):
        self.jobs.user_limit=5
        with self.db:self.db.execute('INSERT INTO fashn_external_spend VALUES(?,?,?)',('benchmark','owner',3))
        with self.assertRaises(ValueError):self.enqueue()
        self.client.submit_tryon.assert_not_called()
    def test_delete_queued_repair_keeps_incurred_cost(self):
        self.jobs.reviewer.review.return_value=self.bad
        self.enqueue();self.jobs.tick();self.jobs.tick();self.jobs.tick()
        self.assertEqual(self.result()['credits_reserved_or_used'],6)
        self.jobs.delete('owner')
        self.assertEqual(self.jobs.spent('owner'),3)
        self.assertFalse(self.jobs.tick())

    def test_two_provider_jobs_in_flight_and_polling_is_fair(self):
        first=self.enqueue()[0]
        second=self.enqueue(base='second-avatar')[0]
        third=self.enqueue(base='third-avatar')[0]
        self.jobs.tick();self.jobs.tick()
        self.assertEqual(self.client.submit_tryon.call_count,2)
        self.client.poll=Mock(return_value=({'status':'processing'},None))
        self.jobs.tick();self.jobs.tick()
        self.assertEqual(self.client.submit_tryon.call_count,2)
        rows={i:json.loads(m).get('last_poll_at') for i,m in self.db.execute('SELECT id,metadata FROM fashn_jobs')}
        self.assertIsNotNone(rows[first]);self.assertIsNotNone(rows[second]);self.assertIsNone(rows[third])
    def test_app_initializes_tables_before_starting_resumed_worker(self):
        from unittest.mock import patch
        from pilot import create_app
        starts=[]
        def check_start(jobs):
            if jobs.autostart:
                tables={r[0] for r in jobs.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue({'garments','avatar_profiles','weather_profiles'}<=tables)
                starts.append(True)
        with patch.object(FashnJobs,'kick',check_start):
            app=create_app(store_path=':memory:',fashn_client=self.client,fashn_autostart=True)
        self.assertEqual(starts,[True])
        app.extensions['pilot_pool'].shutdown();app.extensions['pilot_store'].db.close()
