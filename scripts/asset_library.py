#!/usr/bin/env python3
"""Shared asset library: explicit review, exact-key reuse and growth planning.

Offline only: this module NEVER calls Tripo or a network service. 3D assets
must actually exist before they are registered. Validation is an explicit
human-reviewed Blender report, never a guessed automatic success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from scene_builder import (
    check_asset_id, check_project, gate, glb_header, jread, jwrite, now,
    rootproject,
)

VERSION = '0.8'
ACCEPTED = {'independent_asset', 'repeated_asset', 'continuous_environment', 'supporting_structure'}
CATEGORIES = {'building', 'vegetation', 'boat', 'vehicle', 'prop', 'rock', 'furniture', 'structure', 'creature', 'other'}


def default_library():
    """Shared across projects; explicit --library takes priority over the environment."""
    return str(Path(os.environ.get('BLENDER_ASSET_LIBRARY') or
                    Path.home() / 'Documents' / 'Codex' / 'SharedAssetLibrary').expanduser().resolve())

def safe_id(value, name='identifier'):
    if not isinstance(value, str):
        raise ValueError(name + ' must be a string')
    return check_asset_id(value)


def library_root(path):
    return Path(path).expanduser().resolve()


def load_library(path, create=False):
    p=library_root(path)
    index=p/'catalog.json'
    if not index.exists():
        if not create:
            raise ValueError('Shared asset library not initialized. Run: asset_library.py init --library <folder>')
        p.mkdir(parents=True, exist_ok=True)
        jwrite(index, {'schema_version':VERSION, 'assets':[], 'created_at':now()})
    data=jread(index)
    if not isinstance(data.get('assets'),list):
        raise ValueError('Invalid library catalog')
    return p, data


def hashfile(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def catalogue_match(catalog, library, *, asset_key, category, style_id, requirements=None, asset_type='glb_model'):
    """Strict deterministic match. Never match just because two objects share a category."""
    requirements = requirements or {}
    matches=[]
    for a in catalog['assets']:
        if a.get('asset_type','glb_model') != asset_type:
            continue
        # Single-image reuse currently means an albedo slot, never a normal/roughness map.
        if asset_type == 'texture' and a.get('texture_role', 'albedo') != 'albedo':
            continue
        if a.get('asset_key') != asset_key or a.get('category') != category:
            continue
        if a.get('style_id') != style_id:
            continue
        if a.get('status') != 'validated':
            continue
        if not a.get('license',{}).get('allow_project_reuse',False):
            continue
        capabilities=a.get('capabilities',{})
        if any(need and not capabilities.get(name,False) for name,need in requirements.items()):
            continue
        rel=a.get('model_path')
        if not rel or Path(rel).is_absolute():
            continue
        path=(library/rel).resolve()
        if not path.is_relative_to(library.resolve()) or not path.is_file():
            continue
        try:
            if asset_type=='glb_model':
                glb_header(path)
            elif asset_type=='texture':
                from mock_asset_pipeline import validate_real_image
                validate_real_image(path)
            else:
                continue
        except (ValueError,OSError):
            continue
        if hashfile(path) != a.get('sha256'):
            continue
        matches.append(a)
    return sorted(matches,key=lambda a:(a.get('asset_id',''),a.get('registered_at','')))


def cmd_init(args):
    p,d=load_library(args.library,create=True)
    print('LIBRARY READY',p,'assets',len(d['assets']))


def cmd_register(args):
    p,catalog=load_library(args.library)
    aid=safe_id(args.id,'asset_id'); key=safe_id(args.key,'asset_key')
    cat=args.category
    if cat not in CATEGORIES:
        raise ValueError('Unsupported category: '+cat)
    style=safe_id(args.style_id,'style_id')
    if any(a['asset_id']==aid for a in catalog['assets']):
        raise ValueError('Asset ID already registered. Create a new version/ID rather than overwrite: '+aid)
    src=Path(args.glb).expanduser().resolve()
    file_info=glb_header(src)
    dest=p/'models'/cat/aid/'raw.glb'
    if dest.exists():
        raise ValueError('Model destination already exists: '+str(dest))
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)
    # License reuse is opt-in, and independent of the user's right to possess the original file.
    entry={
        'asset_id':aid,'asset_key':key,'asset_type':'glb_model','name':args.name or aid,
        'category':cat,'style_id':style,'model_path':dest.relative_to(p).as_posix(),
        'sha256':file_info['sha256'],'bytes':file_info['size_bytes'],
        'source':args.source,'tags':sorted(set((args.tags or '').split(',')) - {''}),
        'license':{'allow_project_reuse':bool(args.allow_reuse),'notes':args.license_note or 'not supplied'},
        'capabilities':{},'status':'registered_unverified','registered_at':now(),
        'review':None
    }
    catalog['assets'].append(entry)
    jwrite(p/'catalog.json',catalog)
    print('REGISTERED UNVERIFIED',aid,'=>',dest)
    print('NEXT: Blender review and approval with actual report. No automatic reuse yet.')



def cmd_register_texture(args):
    from mock_asset_pipeline import validate_real_image
    p,catalog=load_library(args.library)
    aid=safe_id(args.id);key=safe_id(args.key)
    cat=args.category
    if cat not in CATEGORIES:raise ValueError('Unsupported category')
    style=safe_id(args.style_id)
    if any(a['asset_id']==aid for a in catalog['assets']):
        raise ValueError('Asset ID already registered: '+aid)
    src=Path(args.image).expanduser().resolve()
    _w,_h,ext=validate_real_image(src)
    dest=p/'textures'/cat/aid/('albedo.'+ext)
    if dest.exists():raise ValueError('Texture destination exists; not overwriting')
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)
    entry={'asset_id':aid,'asset_key':key,'asset_type':'texture','name':args.name or aid,
           'category':cat,'style_id':style,'model_path':dest.relative_to(p).as_posix(),
           'sha256':hashfile(dest),'bytes':dest.stat().st_size,
           'source':args.source,'tags':sorted(set((args.tags or '').split(',')) - {''}),
           'license':{'allow_project_reuse':bool(args.allow_reuse),'notes':args.license_note or 'not supplied'},
           'capabilities':{},'status':'registered_unverified','registered_at':now(),'review':None}
    catalog['assets'].append(entry);jwrite(p/'catalog.json',catalog)
    print('TEXTURE REGISTERED UNVERIFIED',aid)


def cmd_approve_texture(args):
    p,catalog=load_library(args.library)
    aid=safe_id(args.id)
    asset=next((a for a in catalog['assets'] if a['asset_id']==aid and a.get('asset_type')=='texture'),None)
    if not asset:raise ValueError('Texture not found')
    if not args.confirm_review:raise ValueError('Explicit --confirm-review required')
    if not asset['license']['allow_project_reuse']:raise ValueError('Texture reuse license not granted')
    report_path=Path(args.report).expanduser().resolve()
    report=jread(report_path)
    if report.get('material_preview_ok') is not True:
        raise ValueError('Need material_preview_ok: true from actual image/Blender review')
    if hashfile(p/asset['model_path'])!=asset['sha256']:
        raise ValueError('Texture changed since registration')
    asset['status']='validated'
    asset['review']={'method':'user_confirmed_material_preview','reviewer':args.reviewer,
                     'report_sha256':hashfile(report_path),'reviewed_at':now(),
                     'note':'User-provided report; not verified by this CLI process.'}
    jwrite(p/'catalog.json',catalog)
    print('TEXTURE APPROVED FOR REUSE',aid)


def cmd_approve(args):
    p,catalog=load_library(args.library)
    aid=safe_id(args.id)
    asset=next((a for a in catalog['assets'] if a['asset_id']==aid),None)
    if not asset:
        raise ValueError('Unknown asset_id')
    if not args.confirm_review:
        raise ValueError('Explicit --confirm-review required after real Blender inspection')
    if not asset['license']['allow_project_reuse']:
        raise ValueError('License reuse not granted; cannot mark as reusable')
    report_path=Path(args.report).expanduser().resolve()
    if not report_path.is_file():
        raise ValueError('Real Blender validation report not found')
    report=jread(report_path)
    fields=['opened_in_blender','geometry_ok','materials_ok','scale_and_origin_ok']
    if any(report.get(f) is not True for f in fields):
        raise ValueError('Validation report must explicitly contain true for: '+', '.join(fields))
    expected=(p/asset['model_path']).resolve()
    if hashfile(expected)!=asset['sha256']:
        raise ValueError('Model changed after registration; re-register version')
    asset['status']='validated'
    asset['capabilities']={k: bool(v) for k,v in report.get('capabilities',{}).items()}
    asset['review']={'method':'user_confirmed_blender_review','reviewer':args.reviewer,
                     'report_sha256':hashfile(report_path),'reviewed_at':now(),
                     'note':'User-provided report; not verified in this CLI process.'}
    jwrite(p/'catalog.json',catalog)
    print('APPROVED FOR REUSE (user-confirmed Blender report)',aid)


def read_analysis(p):
    from mock_asset_pipeline import validate_analysis
    f=p/'scene_elements.json'
    if not f.is_file():
        raise ValueError('Missing scene_elements.json; import analysis first')
    return validate_analysis(jread(f))


def build_plan(p, lib, catalog):
    gate(p)
    analysis=read_analysis(p)
    style=jread(p/'style_guide.json')['style_id']
    entries=[]
    for e in analysis['elements']:
        aid=e['asset_id']; category=e['category']
        if e['kind']=='continuous_environment' or not e.get('tripo_candidate'):
            material_key=e.get('material_key')
            if material_key:
                material_key=safe_id(material_key,'material_key')
                tex=catalogue_match(catalog,lib,asset_key=material_key,category=category,
                                    style_id=style,asset_type='texture')
                if tex:
                    chosen=tex[0]
                    entries.append({'asset_id':aid,'category':category,
                                    'route':'material_library_reuse','library_asset_id':chosen['asset_id'],
                                    'library_texture_path':chosen['model_path'],
                                    'library_sha256':chosen['sha256'],
                                    'reason':'Validated, licensed texture matches style and material key.'})
                else:
                    entries.append({'asset_id':aid,'category':category,
                                    'route':'procedural_material_needs_texture',
                                    'material_key':material_key,
                                    'reason':'Material can be procedural; optional compatible texture missing. Not a Tripo 3D task.'})
            else:
                entries.append({'asset_id':aid,'category':category,'route':'procedural_environment',
                                'reason':'Continuous terrain/surface or not an independent Tripo candidate.',
                                'instances_estimated':e.get('instances_estimated',1)})
            continue
        key=safe_id(e.get('asset_key',aid),'asset_key')
        requirements=e.get('required_capabilities',{})
        if not isinstance(requirements,dict) or any(not isinstance(v,bool) for v in requirements.values()):
            raise ValueError('required_capabilities must be an object of boolean values for '+aid)
        matches=catalogue_match(catalog,lib,asset_key=key,category=category,
                                style_id=style, requirements=requirements)
        if matches:
            match=matches[0]
            entries.append({'asset_id':aid,'asset_key':key,'category':category,
                            'route':'library_reuse','library_asset_id':match['asset_id'],
                            'library_model_path':match['model_path'],
                            'library_sha256':match['sha256'],
                            'reason':'Validated model matched exact key, style, category, capabilities and reuse license.',
                            'instances_estimated':e.get('instances_estimated',1),
                            'scatter_route':'geometry_nodes_instancing' if e['kind']=='repeated_asset' else 'single_placement'})
        else:
            entries.append({'asset_id':aid,'asset_key':key,'category':category,
                            'route':'mock_tripo_request',
                            'reason':'No validated, licensed model matching exact asset key, category, style and capabilities.',
                            'instances_estimated':e.get('instances_estimated',1),
                            'target_base_models':int(e.get('base_variant_count',1)),
                            'scatter_route':'geometry_nodes_instancing' if e['kind']=='repeated_asset' else 'single_placement'})
    return {
        'schema_version':VERSION,'mode':'offline_mock','asset_library_root':str(lib),
        'project_id':check_project(p)['project_id'],'style_id':style,'generated_at':now(),
        'summary':{'reuse':sum(x['route']=='library_reuse' for x in entries),
                   'generate_request':sum(x['route']=='mock_tripo_request' for x in entries),
                   'procedural':sum(x['route'] in ('procedural_environment','procedural_material_needs_texture') for x in entries),
                   'material_reuse':sum(x['route']=='material_library_reuse' for x in entries)},
        'entries':entries,'real_tripo_calls':0
    }


def cmd_plan(args):
    p=rootproject(args.project);check_project(p)
    lib,catalog=load_library(args.library)
    plan=build_plan(p,lib,catalog)
    dest=p/'asset_library_growth_plan.json'
    jwrite(dest,plan)
    print('GROWTH PLAN',json.dumps(plan['summary'],ensure_ascii=False),'->',dest)
    print('No Tripo calls made. Next: apply-reuse, then prepare-mock.')


def cmd_apply(args):
    p=rootproject(args.project);check_project(p);gate(p)
    lib,catalog=load_library(args.library)
    plan_path=p/'asset_library_growth_plan.json'
    if not plan_path.is_file():
        raise ValueError('Generate plan-growth first')
    plan=jread(plan_path)
    if plan['asset_library_root']!=str(lib):
        raise ValueError('Plan library differs; regenerate growth plan')
    if plan['style_id']!=jread(p/'style_guide.json')['style_id']:
        raise ValueError('Plan style changed; regenerate growth plan')
    manifest_path=p/'asset_manifest.json'; mf=jread(manifest_path)
    byid={a['asset_id']:a for a in mf.get('assets',[])}
    copied=0
    # Recompute current plan to prevent reuse of an asset that was revoked or changed.
    current=build_plan(p,lib,catalog)
    indexed={e['asset_id']:e for e in current['entries']}
    for entry in plan['entries']:
        if entry['route'] not in ('library_reuse','material_library_reuse'):
            continue
        refreshed=indexed.get(entry['asset_id'])
        if not refreshed or refreshed.get('route')!=entry['route'] or refreshed.get('library_sha256')!=entry.get('library_sha256'):
            raise ValueError('Library match changed. Regenerate growth plan.')
        aid=entry['asset_id']; check_asset_id(aid)
        model=(lib/entry.get('library_model_path', entry.get('library_texture_path',''))).resolve()
        if not model.is_relative_to(lib) or not model.is_file():
            raise ValueError('Shared model missing')
        ext='.glb' if entry['route']=='library_reuse' else model.suffix.lower()
        dest=p/'assets'/('library_reuse' if ext=='.glb' else 'library_textures')/(aid+ext)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if hashfile(dest)!=entry['library_sha256']:
                raise ValueError('Existing project asset differs; will not overwrite: '+aid)
        else:
            shutil.copy2(model,dest);copied+=1
        a=byid.get(aid,{'asset_id':aid})
        if a.get('task_id') or (a.get('model_path') and a['model_path']!=dest.relative_to(p).as_posix()):
            raise ValueError('Project asset already has a model/task; do not silently replace: '+aid)
        reused_model=entry['route']=='library_reuse'
        a.update({'name':a.get('name',aid), 'category':entry['category'],
                  'geometry_source':'asset_library' if reused_model else 'procedural_material',
                  'generation_route':'asset_library' if reused_model else 'material_library',
                  'library_asset_id':entry['library_asset_id'],
                  ('model_path' if reused_model else 'texture_path'):dest.relative_to(p).as_posix(),
                  'file_sha256':entry['library_sha256'],'use_placeholder':False,
                  'status':'library_reused_pending_blender_import' if reused_model else 'material_reused_pending_setup',
                  'tripo_candidate':False,'instances_estimated':entry.get('instances_estimated',1),
                  'scatter_route':entry.get('scatter_route','material_surface')})
        byid[aid]=a
    mf['assets']=list(byid.values())
    mf['schema_version']=VERSION
    jwrite(manifest_path,mf)
    print('REUSE APPLIED',len([e for e in plan['entries'] if e['route'] in ('library_reuse','material_library_reuse')]),
          'asset references;',copied,'model files copied; none sent to Tripo')


def cmd_search(args):
    lib,catalog=load_library(args.library)
    matches=catalogue_match(catalog,lib,asset_key=safe_id(args.key),
        category=args.category,style_id=safe_id(args.style_id))
    print(json.dumps([{'asset_id':a['asset_id'],'asset_key':a['asset_key'],'model_path':a['model_path'],
                       'style_id':a['style_id'],'status':a['status']} for a in matches],ensure_ascii=False,indent=2))


def cmd_list(args):
    lib,catalog=load_library(args.library)
    print(json.dumps({'library':str(lib),'assets':catalog['assets']},ensure_ascii=False,indent=2))


def main(argv=None):
    ap=argparse.ArgumentParser(description='Shared offline asset library and cold-start planning; no external API calls.')
    sub=ap.add_subparsers(dest='command',required=True)
    a=sub.add_parser('init');a.add_argument('--library',required=True);a.set_defaults(action=cmd_init)
    a=sub.add_parser('register-model');
    for n in ('library','id','key','category','style-id','glb'):
        a.add_argument('--'+n,required=True)
    for n in ('name','tags','source','license-note'):
        a.add_argument('--'+n,default='')
    a.add_argument('--allow-reuse',action='store_true');a.set_defaults(action=cmd_register)
    a=sub.add_parser('register-texture');
    for n in ('library','id','key','category','style-id','image'):a.add_argument('--'+n,required=True)
    for n in ('name','tags','source','license-note'):a.add_argument('--'+n,default='')
    a.add_argument('--allow-reuse',action='store_true');a.set_defaults(action=cmd_register_texture)
    a=sub.add_parser('approve-texture');
    for n in ('library','id','report','reviewer'):a.add_argument('--'+n,required=True)
    a.add_argument('--confirm-review',action='store_true');a.set_defaults(action=cmd_approve_texture)
    a=sub.add_parser('approve-model');
    for n in ('library','id','report','reviewer'):a.add_argument('--'+n,required=True)
    a.add_argument('--confirm-review',action='store_true');a.set_defaults(action=cmd_approve)
    a=sub.add_parser('plan-growth');a.add_argument('--project',required=True);a.add_argument('--library',required=True);a.set_defaults(action=cmd_plan)
    a=sub.add_parser('apply-reuse');a.add_argument('--project',required=True);a.add_argument('--library',required=True);a.set_defaults(action=cmd_apply)
    a=sub.add_parser('search');
    for n in ('library','key','category','style-id'):a.add_argument('--'+n,required=True)
    a.set_defaults(action=cmd_search)
    a=sub.add_parser('list');a.add_argument('--library',required=True);a.set_defaults(action=cmd_list)
    # The same default applies to legacy commands and folder ingestion.
    for parser in sub.choices.values():
        for action in parser._actions:
            if action.dest == 'library':
                action.required = False
                action.default = default_library()
    args=ap.parse_args(argv)
    try:
        args.action(args)
        return 0
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,json.JSONDecodeError) as e:
        print('ERROR:',e,file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
