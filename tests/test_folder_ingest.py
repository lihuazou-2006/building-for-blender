"""Observable folder ingest invariants; temporary libraries, no Blender/network."""
import json
import os
import sys
import tempfile
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import folder_ingest as ingest
import asset_library as lib
from test_library_growth import triangle_glb


class FolderIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / '用户素材'
        self.source.mkdir()
        self.library = self.root / 'library'

    def scan(self):
        return ingest.scan(self.source, self.library)

    def test_glb_content_classification_and_duplicate_import(self):
        p = triangle_glb(self.source / 'rock.glb')
        report = self.scan()
        self.assertEqual(report['entries'][0]['inspection']['mesh_count'], 1)
        self.assertEqual(report['entries'][0]['classification']['category'], 'rock')
        first = ingest.import_report(report)
        second = ingest.import_report(report)
        self.assertEqual(len(first['added']), 1)
        self.assertEqual(second['added'], [])
        self.assertEqual(len(second['duplicates']), 1)
        _, catalog = lib.load_library(self.library)
        entry = catalog['assets'][0]
        self.assertEqual((self.library / entry['model_path']).read_bytes(), p.read_bytes())
        self.assertEqual(entry['status'], 'registered_unverified')
        self.assertFalse(entry['license']['allow_project_reuse'])
        self.assertEqual(lib.catalogue_match(catalog, self.library, asset_key='rock', category='rock', style_id='unknown'), [])

    def test_internal_obj_names_and_companion_files_preserved(self):
        (self.source / '001.obj').write_text('o coastal_grass\nmtllib grass.mtl\nv 0 0 0\n', encoding='utf-8')
        (self.source / 'grass.mtl').write_text('newmtl grass\nmap_Kd tex/leaf.png\n')
        (self.source / 'tex').mkdir()
        (self.source / 'tex' / 'leaf.png').write_bytes(b'not_a_valid_image')
        report = self.scan()
        obj = next(e for e in report['entries'] if e['relative_path'].endswith('.obj'))
        self.assertEqual(obj['classification']['category'], 'vegetation')
        result = ingest.import_report(report)
        snapshot = Path(result['source_snapshot'])
        for original in self.source.rglob('*'):
            if original.is_file():
                self.assertEqual(original.read_bytes(), (snapshot / original.relative_to(self.source)).read_bytes())
        _, catalog = lib.load_library(self.library)
        self.assertEqual(catalog['assets'][0]['asset_type'], 'source_model')
        self.assertEqual(len(result['failed']), 1)

    def test_glb_internal_names_identify_generic_filename(self):
        p = triangle_glb(self.source / '001.glb')
        data = p.read_bytes()
        chunk_size = struct.unpack('<I', data[12:16])[0]
        doc = json.loads(data[20:20 + chunk_size])
        doc['meshes'][0]['name'] = 'GrassClump'
        body = json.dumps(doc).encode()
        body += b' ' * (-len(body) % 4)
        tail = data[20 + chunk_size:]
        p.write_bytes(struct.pack('<III', 0x46546c67, 2, 20 + len(body) + len(tail)) +
                      struct.pack('<I4s', len(body), b'JSON') + body + tail)
        entry = self.scan()['entries'][0]
        self.assertEqual(entry['classification']['category'], 'vegetation')
        self.assertEqual(entry['classification']['asset_key'], 'grass_clump')

    def test_source_change_rejected_before_library_write(self):
        triangle_glb(self.source / 'rock.glb')
        report = self.scan()
        (self.source / 'new.txt').write_text('added after scan')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            ingest.import_report(report)
        self.assertFalse(self.library.exists())

    def test_visual_analysis_hash_and_classification(self):
        triangle_glb(self.source / '001.glb')
        report = self.scan()
        row = report['entries'][0]
        analysis = {'entries': [{'relative_path': '001.glb', 'source_sha256': row['sha256'],
                    'category': 'vegetation', 'asset_key': 'coastal_grass_clump', 'style_id': 'japanese_cel',
                    'evidence': 'Test inspection fixture: grass blades in model preview'}]}
        ingest.import_report(report, analysis, True, 'test license')
        _, catalog = lib.load_library(self.library)
        entry = catalog['assets'][0]
        self.assertEqual(entry['category'], 'vegetation')
        self.assertEqual(entry['semantic_review'], 'completed')
        self.assertEqual(entry['status'], 'registered_unverified')

    def test_stale_analysis_rejected(self):
        triangle_glb(self.source / '001.glb')
        report = self.scan()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            ingest.import_report(report, {'entries': [{'relative_path': '001.glb', 'source_sha256': 'wrong', 'evidence': 'x'}]})
        self.assertFalse(self.library.exists())

    def test_nested_library_not_rescanned(self):
        self.library = self.source / 'shared'
        triangle_glb(self.source / 'rock.glb')
        ingest.import_report(self.scan())
        report = self.scan()
        self.assertEqual(len(report['files']), 1)

    def test_gltf_external_path_escape_rejected(self):
        (self.source / 'unsafe.gltf').write_text(json.dumps({'buffers': [{'uri': '../secret.bin'}]}))
        with self.assertRaisesRegex(ValueError, 'Invalid relative path'):
            ingest.import_report(self.scan())
        self.assertFalse(self.library.exists())

    def test_gltf_dependencies_kept_and_changes_not_deduplicated(self):
        (self.source / 'mesh.gltf').write_text(json.dumps({'buffers': [{'uri': 'buffer.bin'}]}))
        (self.source / 'buffer.bin').write_bytes(b'first')
        first = ingest.import_report(self.scan())
        (self.source / 'buffer.bin').write_bytes(b'second')
        second = ingest.import_report(self.scan())
        self.assertEqual(len(first['added']), 1)
        self.assertEqual(len(second['added']), 1)
        _, catalog = lib.load_library(self.library)
        for entry in catalog['assets']:
            self.assertTrue((self.library / entry['model_path']).is_file())
            self.assertTrue((self.library / entry['model_path']).with_name('buffer.bin').is_file())

    def test_pbr_maps_not_selected_as_albedo(self):
        from PIL import Image
        for name in ('rock_normal.png', 'rock_albedo.png', 'holiday.png'):
            Image.new('RGB', (256, 256), 'green').save(self.source / name)
        report = self.scan()
        mapping = ingest.previews(report, self.root / 'previews')
        self.assertEqual(len(mapping), 3)
        ingest.import_report(report)
        _, catalog = lib.load_library(self.library)
        normal = next(a for a in catalog['assets'] if a['texture_role'] == 'normal')
        normal['status'] = 'validated'
        normal['license']['allow_project_reuse'] = True
        self.assertEqual(lib.catalogue_match(catalog, self.library, asset_key='rock', category='rock',
                                            style_id='unknown', asset_type='texture'), [])
        self.assertEqual(next(a for a in catalog['assets'] if a['name'] == 'holiday')['asset_type'], 'reference_image')

    def test_cli_default_library_and_paths_with_spaces(self):
        triangle_glb(self.source / 'rock.glb')
        report = self.root / 'scan report.json'
        with patch.dict(os.environ, {'BLENDER_ASSET_LIBRARY': str(self.library)}):
            code = ingest.main(['import-folder', '--source', str(self.source), '--report', str(report)])
            self.assertEqual(code, 0)
            self.assertTrue((self.library / 'catalog.json').exists())
            self.assertEqual(lib.main(['list']), 0)


if __name__ == '__main__':
    unittest.main()
