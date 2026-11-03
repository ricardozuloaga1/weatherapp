import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from pilot import create_app
from test_fashn import Client

class PhotoPreviewTests(unittest.TestCase):
    def test_preview_keeps_original_photo_avatar_and_library(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app(store_path=str(Path(directory)/'pilot.sqlite3'),fashn_client=Client(),fashn_autostart=False)
            client=app.test_client();client.get('/pilot')
            with client.session_transaction() as session: owner=session['owner'];csrf=session['csrf']
            def photo(color):
                f=io.BytesIO();Image.new('RGB',(640,960),color).save(f,'PNG');return f.getvalue()
            original=photo('red');new=photo('blue')
            jobs=app.extensions['fashn'];base,_=jobs.enqueue(owner,original,'base');jobs.tick();jobs.tick();jobs.approve(owner,base)
            client.post('/api/pilot/photo',data={'photo':(io.BytesIO(original),'original.png')},headers={'X-CSRF-Token':csrf})
            saved_photo=client.get('/api/pilot/photo').data
            response=client.post('/api/fashn/photo-preview',data={'photo':(io.BytesIO(new),'new.png'),'consent':'true'},headers={'X-CSRF-Token':csrf})
            self.assertEqual(response.status_code,202);self.assertNotEqual(response.json['id'],base)
            jobs.tick();jobs.tick()
            self.assertEqual(jobs.approved(owner),base)
            self.assertEqual(client.get('/api/pilot/photo').data,saved_photo)
            self.assertIsNotNone(jobs.image(owner,base))
            self.assertEqual(client.post('/api/fashn/photo-preview').status_code,403)
            self.assertEqual(client.post('/api/fashn/photo-preview',headers={'X-CSRF-Token':csrf}).status_code,400)
