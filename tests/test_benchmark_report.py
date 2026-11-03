import json,tempfile,unittest
from pathlib import Path
from pilot import create_app
from test_fashn import Client,image

class BenchmarkReportTests(unittest.TestCase):
    def test_owner_only_report_and_images(self):
        app=create_app(store_path=':memory:',fashn_client=Client(),fashn_autostart=False)
        try:
            with tempfile.TemporaryDirectory() as folder:
                app.config['BENCHMARK_DIR']=folder;root=Path(folder)
                owner=app.test_client();owner.get('/')
                with owner.session_transaction() as s:oid=s['owner']
                avatar=app.extensions['fashn'].import_studio(oid,image())
                (root/'manifest.json').write_text(json.dumps({'avatar':avatar}))
                (root/'report.html').write_text('<h1>Private results</h1>')
                (root/'avatar.png').write_bytes(image())
                with owner.get('/benchmark/') as r:self.assertEqual(r.status_code,200)
                with owner.get('/benchmark/avatar.png') as r:self.assertEqual(r.status_code,200)
                other=app.test_client();other.get('/')
                self.assertEqual(other.get('/benchmark/').status_code,404)
                self.assertEqual(other.get('/benchmark/avatar.png').status_code,404)
                self.assertEqual(owner.get('/benchmark/manifest.json').status_code,404)
                self.assertEqual(owner.get('/benchmark/%2e%2e%2fsecret.png').status_code,404)
        finally:
            app.extensions['pilot_pool'].shutdown();app.extensions['pilot_store'].db.close()
