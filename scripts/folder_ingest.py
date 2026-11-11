"""Local folder inventory and batch ingest. Never executes source files or calls APIs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
from pathlib import Path

import asset_library as lib
from scene_builder import jread, jwrite, now, glb_header

MODELS = {'.glb', '.gltf', '.fbx', '.obj', '.blend', '.stl', '.ply'}
IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp', '.exr', '.hdr'}
RULES = [
    ('vegetation', 'grass_clump', ['grass', '草丛', '草地']),
    ('vegetation', 'bush', ['bush', 'shrub', '灌木']),
    ('vegetation', 'tree', ['tree', 'pine', 'oak', '树', '松树']),
    ('vegetation', 'moss', ['moss', '苔藓']),
    ('rock', 'rock', ['rock', 'stone', 'boulder', '岩石', '石头']),
    ('building', 'building', ['house', 'building', '建筑', '房屋']),
    ('boat', 'boat', ['boat', 'ship', '船']),
    ('vehicle', 'vehicle', ['car', 'truck', 'vehicle', '汽车', '车辆']),
    ('furniture', 'furniture', ['chair', 'table', 'furniture', '椅', '桌']),
    ('creature', 'creature', ['animal', 'creature', '动物']),
]
ROLES = {
    'normal': ['normal', 'nrm', '法线'], 'roughness': ['roughness', 'rough', '粗糙'],
    'metallic': ['metallic', 'metalness', '金属度'], 'ao': ['ao', 'occlusion'],
    'height': ['height', 'displacement', '高度', '置换'],
    'albedo': ['albedo', 'basecolor', 'diffuse', 'color', '颜色', '漫反射'],
    'opacity': ['opacity', 'alpha', '透明'],
}


def has_word(text, word):
    return bool(re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', text)) if word.isascii() else word in text


def inventory(root, excluded):
    """Walk all ordinary files, excluding links/junctions and the destination library."""
    files, skipped = [], []
    def walk_error(exc):
        skipped.append({'path': str(exc.filename), 'reason': str(exc)})
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        current = Path(directory)
        kept = []
        for name in sorted(dirs):
            p = current / name
            if p.is_symlink() or getattr(p, 'is_junction', lambda: False)() or p.resolve().is_relative_to(excluded):
                skipped.append({'path': p.relative_to(root).as_posix(), 'reason': 'link_or_library'})
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            p = current / name
            if p.is_symlink() or not p.is_file():
                skipped.append({'path': p.relative_to(root).as_posix(), 'reason': 'not_regular_file'})
                continue
            try:
                files.append({'relative_path': p.relative_to(root).as_posix(),
                              'sha256': lib.hashfile(p), 'bytes': p.stat().st_size})
            except OSError as exc:
                skipped.append({'path': p.relative_to(root).as_posix(), 'reason': str(exc)})
    return sorted(files, key=lambda x: x['relative_path']), skipped


def gltf_document(p):
    if p.suffix.lower() == '.gltf':
        if p.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('glTF JSON exceeds 16 MB metadata limit')
        return jread(p)
    glb_header(p)
    with p.open('rb') as f:
        f.seek(12)
        size, kind = struct.unpack('<I4s', f.read(8))
        if kind != b'JSON' or size > 16 * 1024 * 1024 or size + 20 > p.stat().st_size:
            raise ValueError('Invalid/oversized GLB JSON chunk')
        return json.loads(f.read(size).decode('utf-8'))


def inspect_file(p):
    ext = p.suffix.lower()
    detail = {'method': 'file_metadata', 'names': []}
    if ext in {'.glb', '.gltf'}:
        doc = gltf_document(p)
        if not isinstance(doc, dict):
            raise ValueError('glTF JSON root must be an object')
        detail.update(method='gltf_content', names=[str(x['name']) for group in ('nodes', 'meshes', 'materials')
                      for x in doc.get(group, []) if x.get('name')][:100],
                      mesh_count=len(doc.get('meshes', [])),
                      material_count=len(doc.get('materials', [])),
                      external_uris=[x['uri'] for group in ('buffers', 'images') for x in doc.get(group, [])
                                     if x.get('uri') and not x['uri'].startswith('data:')])
    elif ext == '.obj':
        with p.open('r', encoding='utf-8', errors='replace') as f:
            text = f.read(2 * 1024 * 1024)
        detail.update(method='obj_content', names=re.findall(r'^(?:o|g|usemtl)\s+(.+)$', text, re.M)[:100])
    elif ext in IMAGES:
        try:
            from PIL import Image
            with Image.open(p) as im:
                detail.update(method='image_header', dimensions=list(im.size), mode=im.mode, format=im.format)
                im.verify()
        except ImportError:
            detail['inspection_note'] = 'Install Pillow for image validation and thumbnails'
        except Exception as exc:
            raise ValueError('Image cannot be decoded (may require an HDR/EXR decoder): ' + str(exc))
    else:
        detail['inspection_note'] = 'Content semantics require Agent/Blender preview; not inferred from extension'
    return detail


def classify(relative, detail, style_id):
    # Structural names are evidence, not a substitute for visual inspection.
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(relative) + ' ' + ' '.join(detail['names'])).lower()
    category, key = 'other', 'unknown'
    hits = [(cat, key) for cat, key, words in RULES if any(has_word(text, w) for w in words)]
    if len(set(hits)) == 1:
        category, key = hits[0]
    role = next((role for role, words in ROLES.items() if any(has_word(text, w) for w in words)), 'unknown')
    image = Path(relative).suffix.lower() in IMAGES
    return {'name': Path(relative).stem, 'category': category, 'asset_key': key,
            'style_id': style_id, 'tags': [key] if key != 'unknown' else [],
            'asset_type': ('texture' if role != 'unknown' else 'reference_image') if image else
                          ('glb_model' if Path(relative).suffix.lower() == '.glb' and not detail.get('external_uris') else 'source_model'),
            'texture_role': role if image else None,
            'classification_method': 'path_and_structural_names',
            'semantic_review': 'needed', 'classification_confidence': 'medium' if key != 'unknown' else 'unknown'}


def previews(report, directory):
    """Contact sheets for Agent visual classification; originals stay untouched."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError:
        return []
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = [e for e in report['entries'] if e['state'] == 'ready' and
            Path(e['relative_path']).suffix.lower() in IMAGES]
    mapping = []
    font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'
    font = ImageFont.truetype(str(font_path), 13) if font_path.exists() else ImageFont.load_default()
    for offset in range(0, len(rows), 24):
        page = directory / ('images-%03d.jpg' % (offset // 24 + 1))
        sheet = Image.new('RGB', (1024, 6 * 220), '#333333')
        draw = ImageDraw.Draw(sheet)
        for index, entry in enumerate(rows[offset:offset + 24]):
            x, y = (index % 4) * 256, (index // 4) * 220
            try:
                with Image.open(Path(report['source_root']) / entry['relative_path']) as original:
                    thumbnail = ImageOps.contain(ImageOps.exif_transpose(original).convert('RGB'), (246, 180))
                    sheet.paste(thumbnail, (x + 5, y + 5))
                draw.text((x + 5, y + 187), str(offset + index + 1) + ': ' + entry['relative_path'][-28:],
                          font=font, fill='white')
                mapping.append({'relative_path': entry['relative_path'], 'source_sha256': entry['sha256'],
                                'sheet': str(page.resolve()), 'index': offset + index + 1})
            except (OSError, ValueError):
                continue
        sheet.save(page, quality=85)
    return mapping


def scan(source, library, style_id='unknown'):
    root = Path(source).expanduser().resolve()
    library = Path(library).expanduser().resolve()
    if not root.is_dir() or root == library or root.is_relative_to(library):
        raise ValueError('Source must be an existing folder outside the shared library')
    lib.safe_id(style_id, 'style_id')
    files, skipped = inventory(root, library)
    entries = []
    for item in files:
        rel = item['relative_path']
        if Path(rel).suffix.lower() not in MODELS | IMAGES:
            continue
        row = dict(item)
        try:
            detail = inspect_file(root / rel)
            row.update(inspection=detail, classification=classify(rel, detail, style_id), state='ready')
        except (ValueError, OSError, KeyError, TypeError, struct.error) as exc:
            row.update(state='inspection_failed', error=str(exc))
        entries.append(row)
    return {'schema_version': '0.8.1', 'source_root': str(root), 'library_root': str(library),
            'created_at': now(), 'files': files, 'skipped': skipped, 'entries': entries,
            'summary': {'files': len(files), 'candidates': len(entries),
                        'failed': sum(e['state'] != 'ready' for e in entries)}}


def safe_relative(root, relative):
    p = (root / relative).resolve()
    if Path(relative).is_absolute() or not p.is_relative_to(root) or p == root:
        raise ValueError('Invalid relative path: ' + relative)
    return p


def import_report(report, analysis=None, allow_reuse=False, license_note=''):
    root = Path(report['source_root']).resolve()
    library = Path(report['library_root']).resolve()
    if root == library or root.is_relative_to(library):
        raise ValueError('Source cannot be inside library')
    # Re-inventory prevents changed source files, missing dependencies and symlink substitution.
    files, skipped = inventory(root, library)
    if files != report['files']:
        raise ValueError('Source changed since scan; scan again before importing')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    overrides = {}
    for row in (analysis or {}).get('entries', []):
        relative = row['relative_path']
        if relative in overrides:
            raise ValueError('Duplicate classification override: ' + relative)
        overrides[relative] = row
    candidates = {e['relative_path']: e for e in report['entries']}
    if set(overrides) - set(candidates):
        raise ValueError('Analysis contains paths absent from scan')
    prepared = []
    file_index = {item['relative_path']: item for item in files}
    for e in report['entries']:
        rel = e['relative_path']
        safe_relative(root, rel)
        if rel not in file_index or any(e[k] != file_index[rel][k] for k in ('sha256', 'bytes')):
            raise ValueError('Scan entry differs from file inventory: ' + rel)
        if e['state'] != 'ready':
            continue
        info = dict(e['classification'])
        if rel in overrides:
            row = overrides[rel]
            if row.get('source_sha256') != e['sha256']:
                raise ValueError('Analysis hash mismatch: ' + rel)
            if not row.get('evidence'):
                raise ValueError('Analysis requires inspection evidence: ' + rel)
            for key in ('name', 'category', 'asset_key', 'style_id', 'tags', 'texture_role', 'asset_type'):
                if key in row:
                    info[key] = row[key]
            info.update(classification_method='agent_review', semantic_review='completed', evidence=row['evidence'])
        lib.safe_id(info['asset_key']); lib.safe_id(info['style_id'])
        if info['category'] not in lib.CATEGORIES or not isinstance(info.get('tags'), list):
            raise ValueError('Invalid classification: ' + rel)
        if Path(rel).suffix.lower() in IMAGES and info.get('texture_role') not in set(ROLES) | {'unknown'}:
            raise ValueError('Invalid texture role: ' + rel)
        allowed = {'texture', 'reference_image'} if Path(rel).suffix.lower() in IMAGES else (
            {'glb_model'} if Path(rel).suffix.lower() == '.glb' and not e['inspection'].get('external_uris') else {'source_model'})
        if info['asset_type'] not in allowed:
            raise ValueError('Asset type conflicts with file format: ' + rel)
        # Reject glTF external paths escaping the source folder; do not fetch remote dependencies.
        for uri in e['inspection'].get('external_uris', []):
            from urllib.parse import unquote, urlsplit
            if urlsplit(uri).scheme or uri.startswith('//'):
                raise ValueError('Remote dependency not imported: ' + uri)
            dep = safe_relative(root, str(Path(rel).parent / unquote(uri)))
            if not dep.is_file() or dep.relative_to(root).as_posix() not in {f['relative_path'] for f in files}:
                raise ValueError('Missing glTF dependency: ' + uri)
        prepared.append((e, info))
    library, catalog = lib.load_library(library, create=True)
    snapshot = library / 'sources' / digest
    snapshot.mkdir(parents=True, exist_ok=True)
    # Preserve the complete relative source tree, including MTL, BIN and texture companions.
    # No source file is moved or executed. A second identical import copies nothing.
    for item in files:
        src = safe_relative(root, item['relative_path'])
        dest = safe_relative(snapshot.resolve(), item['relative_path'])
        if dest.exists():
            if lib.hashfile(dest) != item['sha256']:
                raise ValueError('Stored source differs; refusing overwrite: ' + str(dest))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        if lib.hashfile(dest) != item['sha256']:
            raise ValueError('Source changed during copy; rescan required')
    added, duplicates = [], []
    for e, info in prepared:
        external = (Path(e['relative_path']).suffix.lower() in MODELS - {'.glb'} or
                    bool(e['inspection'].get('external_uris')))
        identity = e['sha256'] + (':' + digest if external else '')
        if Path(e['relative_path']).suffix.lower() in IMAGES:
            identity += ':' + str(info.get('texture_role', 'unknown'))
        match = next((a for a in catalog['assets'] if a.get('ingest_identity', a.get('sha256')) == identity
                      and a.get('asset_type', 'glb_model') == info['asset_type']), None)
        if match:
            duplicates.append({'relative_path': e['relative_path'], 'asset_id': match['asset_id']})
            continue
        slug = re.sub(r'[^a-z0-9_-]+', '-', Path(e['relative_path']).stem.lower()).strip('-')[:32] or 'asset'
        aid = slug + '-' + hashlib.sha256((identity + info['asset_type']).encode()).hexdigest()[:16]
        if any(a['asset_id'] == aid for a in catalog['assets']):
            raise ValueError('Asset ID collision; existing entry preserved: ' + aid)
        path = snapshot / e['relative_path']
        if info['asset_type'] in {'glb_model', 'texture', 'reference_image'} and not external:
            group = {'glb_model': 'models', 'texture': 'textures', 'reference_image': 'images'}[info['asset_type']]
            path = library / group / info['category'] / aid / ('original' + Path(e['relative_path']).suffix.lower())
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and lib.hashfile(path) != e['sha256']:
                raise ValueError('Existing asset differs; refusing overwrite')
            if not path.exists():
                shutil.copy2(snapshot / e['relative_path'], path)
        entry = dict(info, asset_id=aid, model_path=path.relative_to(library).as_posix(),
                     sha256=e['sha256'], bytes=e['bytes'], source='user_folder',
                     source_path=str(root / e['relative_path']), source_relative_path=e['relative_path'],
                     source_snapshot=snapshot.relative_to(library).as_posix(), ingest_identity=identity,
                     inspection=e['inspection'], capabilities={}, registered_at=now(), review=None,
                     license={'allow_project_reuse': bool(allow_reuse), 'notes': license_note or 'not supplied'},
                     status='registered_unverified')
        catalog['assets'].append(entry)
        added.append(aid)
    jwrite(library / 'catalog.json', catalog)
    result = {'imported_at': now(), 'source_root': str(root), 'library_root': str(library),
              'source_snapshot': str(snapshot), 'added': added, 'duplicates': duplicates,
              'failed': [e for e in report['entries'] if e['state'] != 'ready'],
              'semantic_review_needed': [a['asset_id'] for a in catalog['assets'] if
                                         a['asset_id'] in added and a.get('semantic_review') != 'completed']}
    jwrite(library / 'imports' / (digest + '.json'), dict(scan=report, analysis=analysis, result=result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('scan-folder', 'import-folder'):
        p = sub.add_parser(name)
        p.add_argument('--source', required=True)
        p.add_argument('--library', default=lib.default_library())
        p.add_argument('--style-id', default='unknown')
        p.add_argument('--report', required=True, help='Scan JSON outside source and library folders')
        p.add_argument('--previews', action='store_true', help='Write image contact sheets beside the report (Pillow)')
        if name == 'import-folder':
            p.add_argument('--analysis', help='Optional hash-bound Agent classification JSON')
            p.add_argument('--allow-reuse', action='store_true')
            p.add_argument('--license-note', default='')
    args = parser.parse_args(argv)
    try:
        source = Path(args.source).expanduser().resolve()
        library = Path(args.library).expanduser().resolve()
        report_path = Path(args.report).expanduser().resolve()
        if report_path.is_relative_to(source) or report_path.is_relative_to(library):
            raise ValueError('Save scan report outside source and library folders')
        if args.command == 'scan-folder':
            report = scan(source, library, args.style_id)
            if args.previews:
                report['previews'] = previews(report, report_path.parent / (report_path.stem + '-previews'))
            jwrite(report_path, report)
            print(json.dumps(report['summary'], ensure_ascii=False), 'REPORT', report_path)
        else:
            report = jread(report_path) if report_path.exists() else scan(source, library, args.style_id)
            if report['source_root'] != str(source) or report['library_root'] != str(library):
                raise ValueError('Report source/library differs; rescan required')
            if args.previews and 'previews' not in report:
                report['previews'] = previews(report, report_path.parent / (report_path.stem + '-previews'))
            jwrite(report_path, report)
            result = import_report(report, jread(args.analysis) if args.analysis else None,
                                   args.allow_reuse, args.license_note)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
