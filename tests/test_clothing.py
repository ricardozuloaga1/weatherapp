import io
import unittest
import os
import time
from unittest.mock import patch
from PIL import Image,ImageChops
from avatar_pipeline import png, clothing_alpha, clothing_edit_mask, compose_clothes
from pilot import create_app

class ClothingTests(unittest.TestCase):
    def test_only_clothing_pixels_can_change(self):
        size=(1024,1536)
        regions={'editable':[[[.2,.25],[.8,.25],[.8,.9],[.2,.9]]], 'protected':[[[.25,.4],[.35,.4],[.35,.6],[.25,.6]]]}
        base=Image.new('RGB',size,(33,74,88));candidate=Image.new('RGB',size,(241,198,22))
        result,checks=compose_clothes(png(base),png(candidate),regions)
        image=Image.open(io.BytesIO(result)).convert('RGB')
        hard,_=clothing_alpha(size,regions)
        outside=ImageChops.invert(hard)
        diff=Image.composite(ImageChops.difference(base,image),Image.new('RGB',size),outside)
        self.assertIsNone(diff.getbbox())
        self.assertNotEqual(base.getpixel((512,800)),image.getpixel((512,800)))
        self.assertEqual(base.getpixel((300,700)),image.getpixel((300,700)))
        self.assertTrue(checks['face_and_frame_fixed'])
        mask=Image.open(io.BytesIO(clothing_edit_mask(png(base),regions)))
        self.assertEqual(mask.getpixel((512,800))[3],0)
        self.assertEqual(mask.getpixel((512,100))[3],255)
        with self.assertRaises(ValueError):compose_clothes(png(base),png(Image.new('RGB',(512,768))),regions)

    def test_edge_margin_allows_fabric_without_exposing_protected_skin(self):
        regions={'editable':[[[.3,.3],[.7,.3],[.7,.8],[.3,.8]]],
                 'protected':[[[.45,.2],[.55,.2],[.55,.5],[.45,.5]]],
                 'edge_margin_px':32,'edge_feather_px':12}
        hard,alpha=clothing_alpha((200,300),regions)
        self.assertEqual(alpha.getpixel((60,180)),255)  # Old silhouette is fully editable.
        self.assertEqual(hard.getpixel((28,180)),255)  # Finite background margin.
        self.assertLess(alpha.getpixel((28,180)),10)  # No hard cut at outer boundary.
        self.assertEqual(alpha.getpixel((27,180)),0)
        self.assertEqual(alpha.getpixel((100,120)),0)  # Skin stays protected after dilation.
        self.assertEqual(hard.getpixel((100,120)),0)
        regions['edge_margin_px']=1000
        with self.assertRaises(ValueError):clothing_alpha((200,300),regions)

    def test_reviewed_matte_excludes_repainted_background(self):
        base=Image.new('RGB',(200,300),'tan')
        generated=Image.new('RGB',base.size,'brown')
        matte=Image.new('L',base.size,0)
        from PIL import ImageDraw
        ImageDraw.Draw(matte).rectangle((80,120,120,200),fill=255)
        regions={'editable':[[[.2,.2],[.8,.2],[.8,.9],[.2,.9]]],'protected':[]}
        result,_=compose_clothes(png(base),png(generated),regions,garment_matte=png(matte))
        result=Image.open(io.BytesIO(result))
        self.assertEqual(result.getpixel((60,150)),base.getpixel((60,150)))
        self.assertEqual(result.getpixel((100,150)),generated.getpixel((100,150)))
        with self.assertRaises(ValueError):
            compose_clothes(png(base),png(generated),regions,garment_matte=png(Image.new('L',(10,10))))

    def test_main_experience_has_no_ratings_or_comparison_controls(self):
        app=create_app(store_path=':memory:');client=app.test_client()
        page=client.get('/pilot').text
        self.assertIn('Your look',page)
        self.assertNotIn('Choose your comparison',page)
        self.assertNotIn('ratings',page)
        self.assertIn('Choose your comparison',client.get('/evaluate').text)
        app.extensions['pilot_pool'].shutdown();app.extensions['pilot_store'].db.close()

    def test_dressing_uses_pinned_base_and_reuses_result(self):
        calls=[]
        base=png(Image.new('RGB',(1024,1536),'red'))
        def renderer(photo,*args,**kwargs):
            calls.append((photo,kwargs['mode']))
            return png(Image.new('RGB',(1024,1536),'blue')), {}
        app=create_app(renderer,':memory:');client=app.test_client();client.get('/pilot')
        with client.session_transaction() as sess:
            owner=sess['owner'];headers={'X-CSRF-Token':sess['csrf']}
        regions={'editable':[[[.2,.3],[.8,.3],[.8,.9],[.2,.9]]],'protected':[]}
        record={'photo':b'original selfie is not used for dressing','jobs':[{'id':'base','status':'done','kind':'avatar','image':base}], 'requests':{},'active_avatar':'different-id','permanent_avatar':'fixed-id','avatars':[{'id':'fixed-id','source_job':'base','head_box':[.35,.04,.3,.22],'region_version':'v1','clothing_regions':{'sun':regions}}]}
        app.extensions['pilot_state'][owner]=record
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}):
            payload={'scenario':'sun','consent':True,'request_id':'test-dress-1','avatar_id':'different-id'}
            response=client.post('/api/pilot/dress',headers=headers,json=payload)
            self.assertEqual(response.status_code,202)
            app.extensions['pilot_pool'].shutdown(wait=True)
            self.assertEqual(calls,[(base,'clothes')])
            self.assertEqual(record['jobs'][-1]['status'],'done')
            self.assertTrue(record['jobs'][-1]['checks']['outside_clothing_unchanged'])
            payload['request_id']='test-dress-2'
            cached=client.post('/api/pilot/dress',headers=headers,json=payload)
            self.assertEqual(cached.json['reused'],1)
            self.assertEqual(len(calls),1)
        app.extensions['pilot_store'].db.close()
