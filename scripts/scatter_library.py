#!/usr/bin/env python3
"""Compile a cautious, per-zone Blender linked-mesh scatter job for reused GLBs.

This runs only locally and generates Python SOURCE; actual execution requires
Blender with the target terrain mesh already loaded. Geometry Nodes adapters
remain an optional future enhancement for very large densities.
"""
import argparse
import json
import hashlib
import sys
from pathlib import Path
from scene_builder import check_project, gate, jread, jwrite, rootproject, check_asset_id, now

ROOT=Path(__file__).resolve().parents[1]

def validate_jobs(p,doc):
    manifest=jread(p/'asset_manifest.json')
    assets={a['asset_id']:a for a in manifest.get('assets',[])}
    if not isinstance(doc.get('jobs'),list) or not doc['jobs']:
        raise ValueError('scatter plan must contain nonempty jobs')
    processed=set(); output=[]
    for raw in doc['jobs']:
        aid=check_asset_id(raw.get('asset_id',''))
        if aid in processed:raise ValueError('Duplicate asset in scatter jobs: '+aid)
        processed.add(aid)
        a=assets.get(aid)
        if not a or a.get('generation_route')!='asset_library' or not a.get('model_path'):
            raise ValueError('Scatter assets must be validated library reuses applied to project: '+aid)
        model=(p/a['model_path']).resolve()
        if not model.is_relative_to(p) or not model.is_file():
            raise ValueError('Missing project GLB '+aid)
        bounds=raw.get('bounds_xy')
        if not isinstance(bounds,list) or len(bounds)!=4:
            raise ValueError('bounds_xy must be [xmin,xmax,ymin,ymax] for '+aid)
        x0,x1,y0,y1=[float(v) for v in bounds]
        if not (x0<x1 and y0<y1 and all(abs(n)<1_000_000 for n in [x0,x1,y0,y1])):
            raise ValueError('Invalid zone bounds for '+aid)
        count=raw.get('count')
        if not isinstance(count,int) or not 1<=count<=300:
            raise ValueError('For test runtime, count must be 1 to 300 for '+aid)
        surface=raw.get('surface_object','SB_terrain')
        if not isinstance(surface,str) or not surface.strip():raise ValueError('surface_object required')
        seed=raw.get('seed',2408)
        if not isinstance(seed,int):raise ValueError('seed must be integer')
        scale=raw.get('scale_range',[.7,1.3])
        if not isinstance(scale,list) or len(scale)!=2 or not all(isinstance(v,(int,float)) for v in scale) or not 0.01<=scale[0]<=scale[1]<=20:
            raise ValueError('Bad scale_range')
        output.append({'asset_id':aid,'model_path':a['model_path'],'count':count,
                       'bounds_xy':[x0,x1,y0,y1],'surface_object':surface,
                       'seed':seed,'scale_range':scale})
    if sum(j['count'] for j in output)>800:
        raise ValueError('Too many per-object instances for Python test fallback; use Geometry Nodes for larger fields')
    return output

def compile_job(args):
    p=rootproject(args.project);pr=check_project(p);gate(p)
    src=Path(args.plan).expanduser().resolve()
    doc=jread(src)
    jobs=validate_jobs(p,doc)
    config={'project_dir':str(p),'project_id':pr['project_id'],'jobs':jobs}
    source=(ROOT/'runtime'/'library_scatter_runtime.py').read_text(encoding='utf-8')
    out=p/'generated'/'mcp_scatter.py'
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists() and not args.replace:
        raise ValueError('Generated scatter script already exists; pass --replace to overwrite the GENERATED script only')
    out.write_text('CONFIG = '+repr(config)+'\n\n'+source,encoding='utf-8')
    jwrite(p/'generated'/'scatter_execution_plan.json',{'schema_version':'0.8',
          'project_id':pr['project_id'],'source_file':str(out),'jobs':jobs,
          'requires_blender':True,'execution_mode':'python_linked_mesh_instances',
          'warning':'Compiled script not executed; open the intended scene in Blender first.',
          'created_at':now()})
    print('SCATTER SCRIPT COMPILED',out)
    print('OPEN scene.blend in Blender, then execute the FULL script through your MCP tool.')
    print('The script will save a separate results/scatter_scene.blend if it succeeds.')

def main(argv=None):
    ap=argparse.ArgumentParser(description='Compile linked-mesh asset scattering for Blender. Does not run Blender.')
    ap.add_argument('compile-scatter',choices=['compile-scatter'])
    ap.add_argument('--project',required=True)
    ap.add_argument('--plan',required=True)
    ap.add_argument('--replace',action='store_true')
    a=ap.parse_args(argv)
    try:compile_job(a);return 0
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as e:
        print('ERROR:',e,file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
