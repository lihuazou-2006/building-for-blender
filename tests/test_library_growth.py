"""Shared asset library cold start/reuse tests. No Blender, Tripo or network involved."""
import argparse
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import asset_library as libtool
import mock_asset_pipeline as mock
import scene_builder as sb
from image_fixture import make_test_image


def ns(**kwargs):return argparse.Namespace(**kwargs)


def triangle_glb(dest):
    # Real GLB 2.0 binary with a triangle mesh; no external libraries required.
    import struct as st
    positions=st.pack('<9f', 0,0,0, 1,0,0, 0,1,0)
    indices=st.pack('<3H', 0,1,2)
    # Pad binary to 4-byte boundary.
    binary=positions+indices+(b'\x00'*((-len(positions)-len(indices))%4))
    doc={
      'asset':{'version':'2.0'}, 'scene':0,'scenes':[{'nodes':[0]}],
      'nodes':[{'mesh':0}],
      'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1}]}],
      'buffers':[{'byteLength':len(binary)}],
      'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36,'target':34962},
                     {'buffer':0,'byteOffset':36,'byteLength':6,'target':34963}],
      'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3',
                     'max':[1,1,0],'min':[0,0,0]},
                   {'bufferView':1,'componentType':5123,'count':3,'type':'SCALAR',
                    'max':[2],'min':[0]}]
    }
    data=json.dumps(doc,separators=(',',':')).encode()
    js=data+b' ' * (-len(data)%4)
    size=12+8+len(js)+8+len(binary)
    dest.write_bytes(st.pack('<III',0x46546c67,2,size)+st.pack('<I4s',len(js),b'JSON')+js
                     +st.pack('<I4s',len(binary),b'BIN\x00')+binary)
    return dest


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.p=self.root/'coast'
        self.lib=self.root/'SharedLibrary'
        sb.init(ns(project=str(self.p),name=None,reference=None,preset='blank',force=False))
        sb.select_style(ns(project=str(self.p),id='japanese_cel'))
        # simple agent-authored analysis fixture
        self.analysis={
            'elements':[
                {'asset_id':'rock_near_water','asset_key':'shore_rock','name':'海岸岩石',
                 'kind':'repeated_asset','category':'rock','observed':['灰色岩石'],
                 'inferred':[], 'instances_estimated':30,'views':['main'], 'tripo_candidate':True},
                {'asset_id':'bush_01','asset_key':'coastal_bush','name':'海滨灌木',
                 'kind':'repeated_asset','category':'vegetation','observed':['绿叶团簇'],
                 'inferred':[], 'instances_estimated':70,'views':['main'],'tripo_candidate':True},
                {'asset_id':'moss_surface','name':'苔藓表面','kind':'continuous_environment',
                 'category':'vegetation','observed':['苔藓覆盖'],
                 'inferred':[],'tripo_candidate':False}
            ]
        }
        source=self.root/'analysis.json';source.write_text(json.dumps(self.analysis),encoding='utf-8')
        mock.import_analysis(ns(project=str(self.p),file=str(source),replace=False))
        libtool.cmd_init(ns(library=str(self.lib)))
    def tearDown(self):self.tmp.cleanup()
    def plan(self):
        libtool.cmd_plan(ns(project=str(self.p),library=str(self.lib)))
        return sb.jread(self.p/'asset_library_growth_plan.json')
    def register(self,allow_reuse=True,style='japanese_cel'):
        glb=triangle_glb(self.root/'rock.glb')
        libtool.cmd_register(ns(library=str(self.lib),id='rock_source_A',key='shore_rock',
                        category='rock',style_id=style,glb=str(glb),name='岩石A',tags='rock,shore',
                        source='user_tripo_generated',license_note='User grants project reuse',allow_reuse=allow_reuse))
    def approve(self):
        report=self.root/'blender_review.json'
        report.write_text(json.dumps({'opened_in_blender':True,'geometry_ok':True,
                  'materials_ok':True,'scale_and_origin_ok':True,'capabilities':{'needs_collision':False}}),encoding='utf-8')
        libtool.cmd_approve(ns(library=str(self.lib),id='rock_source_A',report=str(report),
                            reviewer='user_test',confirm_review=True))
    def test_empty_library_generates_only_missing_assets(self):
        plan=self.plan()
        self.assertEqual(plan['summary'],{'reuse':0,'generate_request':2,'procedural':1,'material_reuse':0})
        mock.prepare_mock(ns(project=str(self.p),no_crops=True))
        q=sb.jread(self.p/'tripo_submission_queue.json')
        self.assertEqual(len(q['items']),2)
        self.assertEqual(q['real_tripo_calls'],0)
        self.assertFalse(any(i['asset_id']=='moss_surface' for i in q['items']))
    def test_registered_unverified_is_not_reused(self):
        self.register()
        self.assertEqual(self.plan()['summary']['reuse'],0)
    def test_reuse_only_validated_then_skip_request(self):
        self.register();self.approve()
        plan=self.plan()
        self.assertEqual(plan['summary'],{'reuse':1,'generate_request':1,'procedural':1,'material_reuse':0})
        libtool.cmd_apply(ns(project=str(self.p),library=str(self.lib)))
        mock.prepare_mock(ns(project=str(self.p),no_crops=True))
        q=sb.jread(self.p/'tripo_submission_queue.json')
        self.assertEqual([i['asset_id'] for i in q['items']],['bush_01'])
        mf=sb.jread(self.p/'asset_manifest.json')
        rock=next(a for a in mf['assets'] if a['asset_id']=='rock_near_water')
        self.assertEqual(rock['generation_route'],'asset_library')
        self.assertTrue((self.p/rock['model_path']).is_file())
        self.assertEqual(rock['instances_estimated'],30)
        self.assertEqual(rock['scatter_route'],'geometry_nodes_instancing')
        self.assertEqual(q['real_tripo_calls'],0)
        # second run is idempotent and retains reuse
        libtool.cmd_apply(ns(project=str(self.p),library=str(self.lib)))
        mock.prepare_mock(ns(project=str(self.p),no_crops=True))
        self.assertEqual(len(sb.jread(self.p/'tripo_submission_queue.json')['items']),1)
    def test_never_match_by_category_alone(self):
        self.register();self.approve()
        src=self.root/'new.json';data=json.loads(json.dumps(self.analysis))
        data['elements'][0]['asset_key']='completely_different_rock'
        src.write_text(json.dumps(data),encoding='utf-8')
        mock.import_analysis(ns(project=str(self.p),file=str(src),replace=True))
        self.assertEqual(self.plan()['summary']['reuse'],0)
    def test_style_mismatch_does_not_reuse(self):
        self.register(style='cinematic_coast');self.approve()
        self.assertEqual(self.plan()['summary']['reuse'],0)
    def test_license_must_allow_reuse(self):
        self.register(allow_reuse=False)
        with self.assertRaises(ValueError):self.approve()
        self.assertEqual(self.plan()['summary']['reuse'],0)
    def test_apply_requires_precomputed_plan(self):
        with self.assertRaises(ValueError):
            libtool.cmd_apply(ns(project=str(self.p),library=str(self.lib)))
    def test_mock_cannot_request_approved_reuse_before_apply(self):
        self.register();self.approve();self.plan()
        with self.assertRaisesRegex(ValueError,'must be applied first'):
            mock.prepare_mock(ns(project=str(self.p),no_crops=True))

    def test_texture_reuse_for_moss_material(self):
        import shutil
        img=make_test_image(self.root/'moss.png')
        libtool.cmd_register_texture(ns(library=str(self.lib),id='moss_color_v1',key='coastal_moss',
              category='vegetation',style_id='japanese_cel',image=str(img),name='苔藓颜色纹理',
              source='user_supplied',tags='moss,surface',license_note='user authorized',allow_reuse=True))
        report=self.root/'texture_report.json'
        report.write_text(json.dumps({'material_preview_ok':True}),encoding='utf-8')
        libtool.cmd_approve_texture(ns(library=str(self.lib),id='moss_color_v1',report=str(report),
                    reviewer='test_author',confirm_review=True))
        d=json.loads(json.dumps(self.analysis))
        d['elements'][2]['material_key']='coastal_moss'
        source=self.root/'analysis_moss.json';source.write_text(json.dumps(d),encoding='utf-8')
        mock.import_analysis(ns(project=str(self.p),file=str(source),replace=True))
        plan=self.plan()
        self.assertEqual(plan['summary']['material_reuse'],1)
        self.assertEqual(plan['summary']['generate_request'],2)
        libtool.cmd_apply(ns(project=str(self.p),library=str(self.lib)))
        manifest=sb.jread(self.p/'asset_manifest.json')
        moss=next(a for a in manifest['assets'] if a['asset_id']=='moss_surface')
        self.assertTrue((self.p/moss['texture_path']).is_file())
        self.assertEqual(moss['generation_route'],'material_library')
        mock.prepare_mock(ns(project=str(self.p),no_crops=True))
        self.assertEqual(len(sb.jread(self.p/'tripo_submission_queue.json')['items']),2)
    def test_unavailable_moss_texture_requires_no_tripo_3d(self):
        d=json.loads(json.dumps(self.analysis))
        d['elements'][2]['material_key']='missing_moss_texture'
        source=self.root/'analysis_moss_missing.json';source.write_text(json.dumps(d),encoding='utf-8')
        mock.import_analysis(ns(project=str(self.p),file=str(source),replace=True))
        plan=self.plan()
        moss=next(e for e in plan['entries'] if e['asset_id']=='moss_surface')
        self.assertEqual(moss['route'],'procedural_material_needs_texture')
        self.assertEqual(plan['summary']['generate_request'],2)
    def test_scatter_compiler_requires_real_reused_model_and_explicit_zone(self):
        from scatter_library import validate_jobs, compile_job
        invalid={'jobs':[{'asset_id':'rock_near_water','count':30,'bounds_xy':[-10,10,0,10]}]}
        with self.assertRaisesRegex(ValueError,'validated library reuses'):
            validate_jobs(self.p,invalid)
        self.register();self.approve();self.plan()
        libtool.cmd_apply(ns(project=str(self.p),library=str(self.lib)))
        valid={'jobs':[{'asset_id':'rock_near_water','count':30,'bounds_xy':[-10,10,0,10],
                        'surface_object':'SB_terrain','seed':123,'scale_range':[0.5,1.25]}]}
        jobfile=self.root/'scatter.json';jobfile.write_text(json.dumps(valid),encoding='utf-8')
        self.assertEqual(validate_jobs(self.p,valid)[0]['count'],30)
        compile_job(ns(project=str(self.p),plan=str(jobfile),replace=False))
        compiled=self.p/'generated'/'mcp_scatter.py'
        self.assertTrue(compiled.is_file())
        compile(compiled.read_text(encoding='utf-8'),str(compiled),'exec')
        with self.assertRaisesRegex(ValueError,'already exists'):
            compile_job(ns(project=str(self.p),plan=str(jobfile),replace=False))
        # Programmatic compiler does not create .blend or claim Blender execution.
        self.assertFalse((self.p/'results'/'scatter_scene.blend').exists())

if __name__=='__main__':unittest.main()
