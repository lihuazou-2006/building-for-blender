import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import mock_asset_pipeline as mockpipe
from scene_builder import jread
from image_fixture import make_test_image

class MockTripoTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.p=Path(self.t.name)/'mock_project'
        self.ref=make_test_image(Path(self.t.name)/'reference.png')
        self.analysis=ROOT/'examples'/'coastal_scene_elements.sample.json'
        self.cmd('init','--project',str(self.p),'--preset','blank','--reference',str(self.ref),script='scene_builder.py',success=True)
    def tearDown(self):self.t.cleanup()
    def cmd(self,*argv,script='mock_asset_pipeline.py',success=False):
        r=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*argv],capture_output=True,text=True)
        if success:self.assertEqual(r.returncode,0,r.stderr)
        return r
    def imported(self):
        self.cmd('import-analysis','--project',str(self.p),'--file',str(self.analysis),success=True)
    def selected(self):
        self.cmd('select-style','--project',str(self.p),'--id','japanese_cel',script='scene_builder.py',success=True)
    def prepared(self):
        self.imported();self.selected();self.cmd('prepare-mock','--project',str(self.p),'--no-crops',success=True)
    def image(self):
        return self.ref
    def test_analysis_counts_and_procedural_excluded(self):
        doc=mockpipe.validate_analysis(jread(self.analysis))
        self.assertEqual(len(doc['elements']),20)
        self.prepared()
        queue=jread(self.p/'tripo_submission_queue.json')
        self.assertEqual(len(queue['items']),13)
        self.assertEqual(queue['real_tripo_calls'],0)
        self.assertFalse(any(x['asset_id']=='sea_water' for x in queue['items']))
    def test_style_gate_enforced(self):
        self.imported()
        r=self.cmd('prepare-mock','--project',str(self.p))
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Style not confirmed',r.stderr)
    def test_request_requires_actual_image(self):
        self.prepared()
        req=jread(self.p/'tripo_requests/coastal_bush_request.json')
        self.assertEqual(req['status'],'missing_reference_images')
        self.assertEqual(req['reference_images'],{})
        self.assertIsNone(req['task_id'])
        self.assertFalse(req['is_submitted'])
        self.assertEqual(jread(self.p/'asset_manifest.json')['assets'][0].get('source_crop_status'), 'skipped_by_user')
        self.assertNotIn('source_crop',str(req['reference_images']))
    def test_ingest_approve_and_queue(self):
        self.prepared()
        self.cmd('ingest-image','--project',str(self.p),'--id','coastal_bush', '--view','main','--image',str(self.image()),success=True)
        req=jread(self.p/'tripo_requests/coastal_bush_request.json')
        self.assertEqual(req['status'],'awaiting_review')
        self.assertTrue((self.p/'req_not_exist.json').exists() is False)
        self.cmd('approve-asset','--project',str(self.p),'--id','coastal_bush',success=True)
        req=jread(self.p/'tripo_requests/coastal_bush_request.json')
        self.assertEqual(req['status'],'approved_for_manual_or_future_submission')
        self.assertFalse(req['is_submitted'])
        self.assertTrue((self.p/req['reference_images']['main']).is_file())
    def test_cannot_approve_when_side_missing(self):
        self.prepared()
        self.cmd('ingest-image','--project',str(self.p),'--id','yellow_coastal_house','--view','main','--image',str(self.image()),success=True)
        r=self.cmd('approve-asset','--project',str(self.p),'--id','yellow_coastal_house')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('side',r.stderr)
    def test_tripo_paid_api_blocked_even_with_confirm(self):
        self.prepared()
        r=self.cmd('tripo-submit','--project',str(self.p),'--id','coastal_bush','--image',str(self.image()),'--confirm-paid',script='scene_builder.py')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('MOCK MODE ACTIVE',r.stderr)
    def test_reject_duplicate_ids(self):
        bad=jread(self.analysis)
        bad['elements'].append(dict(bad['elements'][0]))
        with self.assertRaises(ValueError):mockpipe.validate_analysis(bad)
    def test_reject_unsafe_bbox(self):
        bad=jread(self.analysis)
        bad['elements'][0]['bbox_norm']=[-1,0,1,1]
        with self.assertRaises(ValueError):mockpipe.validate_analysis(bad)
    def test_reject_unknown_image(self):
        self.prepared()
        text=self.p/'fake.png';text.write_text('not actually an image'*30)
        r=self.cmd('ingest-image','--project',str(self.p),'--id','coastal_bush','--view','main','--image',str(text))
        self.assertNotEqual(r.returncode,0)
    def test_prepare_twice_does_not_drop_images(self):
        self.prepared()
        self.cmd('ingest-image','--project',str(self.p),'--id','coastal_bush','--view','main','--image',str(self.image()),success=True)
        self.cmd('prepare-mock','--project',str(self.p),'--no-crops',success=True)
        req=jread(self.p/'tripo_requests/coastal_bush_request.json')
        self.assertEqual(req['status'],'awaiting_review')
        self.assertIn('main',req['reference_images'])
    def test_dynamic_style_candidates(self):
        self.imported()
        candidates={'candidates':[{'style_id':'test_a','name':'A','features':{'palette':['#FFFFFF','#111111'],'render_style':'x'}},
                         {'style_id':'test_b','name':'B','features':{'palette':['#EFEFEF','#222222'],'render_style':'y'}},
                         {'style_id':'test_c','name':'C','features':{'palette':['#DFDFDF','#333333'],'render_style':'z'}}]}
        fp=self.p/'styles.json';fp.write_text(json.dumps(candidates),encoding='utf-8')
        self.cmd('set-style-candidates','--project',str(self.p),'--file',str(fp),success=True)
        self.cmd('select-style','--project',str(self.p),'--id','test_b',script='scene_builder.py',success=True)
        self.assertEqual(jread(self.p/'style_guide.json')['style_id'],'test_b')

if __name__=='__main__': unittest.main()
