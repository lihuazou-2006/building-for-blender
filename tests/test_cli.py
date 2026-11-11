import tempfile, json, struct, subprocess, sys, unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import scene_builder as sb

class SkillCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.p=Path(self.temp.name)/'coast'
    def tearDown(self):self.temp.cleanup()
    def cmd(self,*args):
        return subprocess.run([sys.executable,str(ROOT/'scripts/scene_builder.py'),*args],
                              capture_output=True,text=True,check=False)
    def init(self):
        r=self.cmd('init','--project',str(self.p),'--preset','coastal')
        self.assertEqual(r.returncode,0,r.stderr)
    def select(self):
        r=self.cmd('select-style','--project',str(self.p),'--id','japanese_cel')
        self.assertEqual(r.returncode,0,r.stderr)
    def test_init_and_style_gate(self):
        self.init()
        r=self.cmd('compile','--project',str(self.p))
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Style not confirmed',r.stderr)
        self.select()
        self.assertEqual(sb.jread(self.p/'style_guide.json')['style_id'],'japanese_cel')
        self.assertEqual(self.cmd('compile','--project',str(self.p)).returncode,0)
        self.assertTrue((self.p/'generated/mcp_build.py').exists())
        compile((self.p/'generated/mcp_build.py').read_text(encoding='utf-8'),'builder','exec')
        self.assertFalse((self.p/'results/scene.blend').exists())
        generated=(self.p/'generated/mcp_build.py').read_text(encoding='utf-8')
        self.assertIn('palette',generated)
    def test_no_duplicate_init(self):
        self.init();r=self.cmd('init','--project',str(self.p));self.assertNotEqual(r.returncode,0)
    def test_tripo_reference_task_no_image_claim(self):
        self.init();self.select()
        r=self.cmd('prepare-tripo','--project',str(self.p),'--id','custom_house')
        self.assertEqual(r.returncode,0,r.stderr)
        task=sb.jread(self.p/'tasks/custom_house_reference_task.json')
        self.assertIn('NOT an image',task['note'])
    def test_tripo_paid_gate(self):
        self.init();self.select()
        r=self.cmd('tripo-submit','--project',str(self.p),'--id','custom_house','--image','fake.png')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('MOCK MODE ACTIVE',r.stderr)
    def test_asset_registration_is_not_validation(self):
        self.init();self.select()
        source=Path(self.temp.name)/'test.glb'
        scene=b'{"asset":{"version":"2.0"},"scene":0,"scenes":[{}]}'
        scene+=b' ' * ((4-len(scene)%4)%4)
        size=12+8+len(scene)
        source.write_bytes(struct.pack('<III',0x46546c67,2,size)+struct.pack('<II',len(scene),0x4e4f534a)+scene)
        r=self.cmd('register-asset','--project',str(self.p),'--id','custom_house','--glb',str(source))
        self.assertEqual(r.returncode,0,r.stderr)
        asset=sb.jread(self.p/'asset_manifest.json')['assets'][0]
        self.assertEqual(asset['status'],'registered_unverified')
        self.assertEqual(self.cmd('compile','--project',str(self.p)).returncode,0)
    def test_mock_tripo_api_paths(self):
        c=sb.Tripo('fake-key')
        with mock.patch.object(c,'_call',side_effect=[{'file_token':'file_123'}, {'task_id':'t_123'},
                                                     {'status':'success','output':{'model_url':'https://cdn.example/model.glb'}}]) as call:
            self.assertEqual(c.upload(Path('fake.png')),'file_123')
            self.assertEqual(c.submit('file_123'),'t_123')
            self.assertEqual(c.task('t_123')['status'],'success')
            self.assertEqual(call.call_args.args[0],'/tasks/t_123')
    def test_unsafe_asset_id_rejected(self):
        self.init();self.select()
        r=self.cmd('prepare-tripo','--project',str(self.p),'--id','../../unsafe')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Invalid asset_id',r.stderr)
    def test_missing_blender_is_clear(self):
        self.init();self.select();self.cmd('compile','--project',str(self.p))
        r=self.cmd('run-blender','--project',str(self.p),'--blender','not_a_real_blender_executable_abc')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Blender executable not found',r.stderr)

if __name__=='__main__':unittest.main()
