#!/usr/bin/env python3
"""Offline-first CLI for Blender Scene Builder v0.6, stdlib-only.
Run from any cwd: python scripts/scene_builder.py COMMAND ...
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, copy, re
from pathlib import Path
from datetime import datetime, timezone
from urllib import request

ROOT=Path(__file__).resolve().parent.parent
SCHEMA='0.8'
STYLE_IDS={
    'cinematic_coast':('电影感自然海岸',['#C7AE7A','#537CA0','#B4BB95'],'PBR',0.3),
    'japanese_cel':('日式赛璐璐',['#EACA8D','#66A2C2','#71B181'],'NPR',0.65),
    'storybook':('手绘绘本',['#D7AF88','#7CA5A8','#9B9B75'],'hand_painted',0.7),
    'miniature':('微缩模型',['#F0C77A','#5AA0AD','#70A377'],'diorama',0.8),
}

def now(): return datetime.now(timezone.utc).isoformat()
def jread(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def jwrite(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+'.tmp')
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temp.replace(p)
def rootproject(raw):return Path(raw).expanduser().resolve()
def inside(p,base):
    p=Path(p).resolve()
    if not p.is_relative_to(base.resolve()):raise ValueError('Path outside project: '+str(p))
    return p

def check_project(p):
    if not (p/'project.json').is_file():raise ValueError('Project is not initialized: '+str(p))
    d=jread(p/'project.json')
    if not d.get('project_id'):raise ValueError('Missing project_id')
    return d

def init(args):
    p=rootproject(args.project)
    p.mkdir(exist_ok=True,parents=True)
    if (p/'project.json').exists() and not args.force:
        raise ValueError('Project already exists; no overwrite by default')
    if args.force and (p/'project.json').exists():
        raise ValueError('Safety: --force overwrite intentionally disabled; use a new project folder')
    for d in ['assets','references','generated','results','tasks','asset_library','tripo_requests']:(p/d).mkdir(exist_ok=True)
    src=Path(args.reference).expanduser().resolve() if args.reference else None
    reference=None
    if src:
        if not src.is_file():raise ValueError('Reference image not found: '+str(src))
        dst=p/'references'/src.name
        if src!=dst:shutil.copy2(src,dst)
        reference=str(dst.relative_to(p))
    jwrite(p/'project.json',{'schema_version':SCHEMA,'project_id':args.name or p.name,
                            'reference_image':reference,'preset':args.preset,'execution_mode':'mock_tripo','created_at':now()})
    candidates={'selection_status':'awaiting_selection','candidates':[
       {'style_id':sid,'name':name,'features':{'palette':colors,'render_style':mode},
        'complexity_hint':'demo/reference only'} for sid,(name,colors,mode,_) in STYLE_IDS.items()]}
    jwrite(p/'style_candidates.json',candidates)
    jwrite(p/'style_choice.json',{'selection_status':'awaiting_selection','selected_style_id':None,'selection_source':None})
    jwrite(p/'asset_manifest.json',{'schema_version':SCHEMA,'assets':[
       {'asset_id':'custom_house','name':'自定义海湾建筑（示例）','category':'building','geometry_source':'ai_tripo',
        'generation_method':'image_to_3d','reference_image':None,'model_path':None,
        'dimensions':[4.5,4.0,4.5],'placement':[-16,7,0.2],
        'refinement':{'origin':'bottom_center','collision':'box_proxy','structure':'manual_review'},
        'use_placeholder':True,'status':'planned','task_id':None}
    ] if args.preset=='coastal' else []})
    jwrite(p/'scene_blueprint.json',{'schema_version':SCHEMA,'project_id':args.name or p.name,
        'reference_image':reference,'scene_type':args.preset,'bounds_m':[-36,36,-26,31],
        'notes':['This is an editable demo layout, not image-to-3D reconstruction.'],
        'camera':{'position':[44,-58,39],'target':[0,3,1],'projection':'ORTHO','ortho_scale':85}})
    jwrite(p/'spatial_plan.json',{'schema_version':SCHEMA,'seed':2408,
      'zones':[{'zone_id':'water','purpose':'continuous_environment'},
               {'zone_id':'beach','purpose':'shoreline'},
               {'zone_id':'hillside','purpose':'vegetation'},
               {'zone_id':'village','purpose':'buildings'}]})
    print('CREATED',p);print('NEXT: styles --project "'+str(p)+'"')

def styles(args):
    p=rootproject(args.project);check_project(p)
    for item in jread(p/'style_candidates.json')['candidates']:
        print(item['style_id']+' : '+item['name'])
    print('User must explicitly choose: select-style --project ... --id <style_id>')

def select_style(args):
    p=rootproject(args.project);check_project(p)
    options={i['style_id']:i for i in jread(p/'style_candidates.json')['candidates']}
    if args.id not in options:raise ValueError('Not a candidate style ID')
    choice=jread(p/'style_choice.json')
    if choice['selection_status']=='confirmed' and choice['selected_style_id']!=args.id:
        raise ValueError('Style already locked; use a fresh project for this test or explicit migration later')
    c=options[args.id]
    jwrite(p/'style_choice.json',{'selection_status':'confirmed','selected_style_id':args.id,
        'selection_source':'user_explicit_cli','confirmed_at':now()})
    jwrite(p/'style_guide.json',{'schema_version':SCHEMA,'style_id':args.id,'style_name':c['name'],
        'render_style':c['features']['render_style'],'palette':c['features']['palette'],
        'style_revision':1,'confirmed':True})
    print('STYLE LOCKED',args.id)

def gate(p):
    choice=jread(p/'style_choice.json')
    guide=p/'style_guide.json'
    if choice.get('selection_status')!='confirmed' or not guide.exists():
        raise ValueError('Style not confirmed. Run styles + select-style first.')
    if jread(guide).get('style_id')!=choice.get('selected_style_id'):
        raise ValueError('Style guide mismatch')


def status(args):
    p=rootproject(args.project);d=check_project(p)
    m=jread(p/'asset_manifest.json');ch=jread(p/'style_choice.json')
    print(json.dumps({'project_id':d['project_id'],'style':ch,
        'assets':[{'asset_id':a['asset_id'],'status':a['status'],'task_id':a.get('task_id')} for a in m['assets']],
        'generated_build':(p/'generated/mcp_build.py').is_file(),
        'scene_blend':(p/'results/scene.blend').is_file()},ensure_ascii=False,indent=2))

def compile_scene(args):
    p=rootproject(args.project);d=check_project(p);gate(p)
    m=jread(p/'asset_manifest.json');bp=jread(p/'scene_blueprint.json')
    config={'project_dir':str(p),'project_id':d['project_id'],
            'palette':jread(p/'style_guide.json')['palette'],
            'camera':bp.get('camera',{}),'seed':jread(p/'spatial_plan.json').get('seed',2408),
            'render_preview':args.render,'assets':m.get('assets',[])}
    preamble='CONFIG = '+repr(config)+'\n\n'
    source=(ROOT/'runtime'/'builder_template.py').read_text(encoding='utf-8')
    dest=p/'generated'/'mcp_build.py';dest.write_text(preamble+source,encoding='utf-8')
    jwrite(p/'generated'/'execution_plan.json',{'builder_file':str(dest),'project_id':d['project_id'],
        'mode':'Blender Python source to run as background script or execute_blender_code',
        'requires_blender':True,'compiled_at':now()})
    print('COMPILED',dest,'bytes',dest.stat().st_size)
    print('NEXT: run-blender --project "'+str(p)+'" --blender "<path-to-blender>"')
    print('Or pass FULL source text of mcp_build.py to execute_blender_code in Codex.')

def run_blender(args):
    p=rootproject(args.project);check_project(p);gate(p)
    script=p/'generated'/'mcp_build.py'
    if not script.exists():raise ValueError('Run compile first')
    exe=shutil.which(args.blender) or args.blender
    if not Path(exe).is_file() and not shutil.which(exe):
        raise ValueError('Blender executable not found: '+str(exe))
    report=p/'results'/'blender_report.json'
    before=report.stat().st_mtime_ns if report.is_file() else None
    cmd=[str(exe),'--background','--factory-startup','--python',str(script)]
    print('RUN',cmd,flush=True)
    result=subprocess.run(cmd,cwd=str(p),check=False)
    if result.returncode:raise RuntimeError('Blender failed with exit code '+str(result.returncode))
    if not report.is_file() or (before is not None and report.stat().st_mtime_ns==before) or not jread(report).get('finished'):
        raise RuntimeError('Blender returned without a fresh successful build report')
    print('BLENDER BUILD COMPLETED',report)

def check_asset_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('Invalid asset_id: only letters, digits, _ and - allowed')
    return value

def glb_header(p):
    import struct
    if not p.exists() or p.stat().st_size<20:raise ValueError('GLB file is too small/missing')
    with p.open('rb') as f:data=f.read(12)
    magic,version,size=struct.unpack('<III',data)
    if magic!=0x46546c67 or version!=2 or size!=p.stat().st_size:
        raise ValueError('Not a valid GLB v2 header or wrong binary size')
    return {'size_bytes':size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def register(args):
    check_asset_id(args.id)
    p=rootproject(args.project);check_project(p)
    src=Path(args.glb).expanduser().resolve();meta=glb_header(src)
    manifest=jread(p/'asset_manifest.json')
    target=next((a for a in manifest['assets'] if a['asset_id']==args.id),None)
    if target is None:raise ValueError('Asset ID not declared in asset manifest')
    dest=p/'assets'/(args.id+'.glb')
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()!=meta['sha256']:
        raise ValueError('A different asset already exists; do not overwrite automatically')
    if src!=dest:shutil.copy2(src,dest)
    target['model_path']=str(dest.relative_to(p))
    target['file_sha256']=meta['sha256']
    target['status']='registered_unverified'
    jwrite(p/'asset_manifest.json',manifest)
    print('REGISTERED (not Blender-validated)',target['asset_id'],dest)

def finalize(args):
    check_asset_id(args.id)
    p=rootproject(args.project);check_project(p)
    rp=p/'results'/'blender_report.json'
    if not rp.is_file():raise ValueError('No Blender report; run scene build first')
    report=jread(rp)
    if not report.get('finished'):raise ValueError('Build report is not finished')
    imported={x['asset_id'] for x in report.get('imported_assets',[])}
    if args.id not in imported:raise ValueError('Asset ID not found in actual Blender import report')
    mf=jread(p/'asset_manifest.json')
    for a in mf['assets']:
        if a['asset_id']==args.id:
            a['status']='imported_pending_visual_review'
            a['blender_validation_report']=str(rp.relative_to(p))
    jwrite(p/'asset_manifest.json',mf)
    print('IMPORTED AND AWAITING VISUAL REVIEW',args.id)

def prepare_tripo(args):
    check_asset_id(args.id)
    p=rootproject(args.project);check_project(p);gate(p)
    mf=jread(p/'asset_manifest.json')
    a=next((a for a in mf['assets'] if a['asset_id']==args.id),None)
    if not a:raise ValueError('Unknown asset ID')
    style=jread(p/'style_guide.json')
    prompt={'asset_id':args.id,'reference_image':a.get('reference_image'),
       'prompt_en':f"Single isolated {a['name']}, clean plain background, full object visible, no other objects; style: {style['style_name']}; color palette: {', '.join(style['palette'])}; 3/4 view; no text or watermarks.",
       'specification':{'dimensions_m':a.get('dimensions'),'purpose':a.get('category'),
           'refinement':a.get('refinement',{})},
       'note':'Prompt text is NOT an image. Generate actual reference image using an image generation tool first.'}
    dst=p/'tasks'/(args.id+'_reference_task.json');jwrite(dst,prompt)
    print('IMAGE PROMPT READY',dst)

def get_key():
    key=os.environ.get('TRIPO_API_KEY','').strip()
    if not key:raise ValueError('Missing TRIPO_API_KEY environment variable')
    return key

class Tripo:
    BASE='https://openapi.tripo3d.ai/v3'
    def __init__(self,key):self.key=key
    def _call(self,path,body=None,multipart=None):
        headers={'Authorization':'Bearer '+self.key}
        if multipart is not None:
            boundary='----sbv06upload'
            data=(('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+multipart.name+'"\r\n'
                   'Content-Type: application/octet-stream\r\n\r\n').encode('utf-8')
                  +multipart.read_bytes()+('\r\n--'+boundary+'--\r\n').encode())
            headers['Content-Type']='multipart/form-data; boundary='+boundary
            method='POST'
        elif body is not None:
            data=json.dumps(body).encode('utf-8');headers['Content-Type']='application/json';method='POST'
        else:data=None;method='GET'
        req=request.Request(self.BASE+path,headers=headers,data=data,method=method)
        with request.urlopen(req,timeout=45) as response:
            raw=json.loads(response.read(2_000_000))
        if raw.get('code')!=0:raise RuntimeError('Tripo API error: '+str(raw.get('code'))+' '+str(raw.get('message','')))
        return raw['data']
    def upload(self,file):return self._call('/files',multipart=file)['file_token']
    def submit(self,token):return self._call('/generation/image-to-model',body={
        'input':token,'model':'v3.1-20260211','texture':True,'pbr':True})['task_id']
    def task(self,id):return self._call('/tasks/'+id)

def tripo_submit(args):
    check_asset_id(args.id)
    p=rootproject(args.project);check_project(p);gate(p)
    if jread(p/'project.json').get('execution_mode')!='live_tripo':
        raise ValueError('MOCK MODE ACTIVE: paid Tripo submission disabled for this project')
    if not args.confirm_paid:raise ValueError('Paid request requires --confirm-paid')
    if args.max_tasks!=1:raise ValueError('For this test version, max-tasks must be exactly 1')
    key=get_key()
    manifest=jread(p/'asset_manifest.json')
    a=next((a for a in manifest['assets'] if a['asset_id']==args.id),None)
    if not a:raise ValueError('Unknown asset ID')
    if a.get('task_id') or a.get('model_path'):
        raise ValueError('Task/model already exists: never resubmit blindly')
    image=Path(args.image).expanduser().resolve()
    if not image.exists() or image.suffix.lower() not in ('.png','.jpg','.jpeg'):
        raise ValueError('Reference image missing/invalid')
    if image.stat().st_size>20*1024*1024:raise ValueError('Image exceeds 20MB')
    # Save image before submission. The agent must have created this independent ref.
    refdir=p/'references';refdir.mkdir(exist_ok=True)
    target=refdir/(args.id+image.suffix.lower())
    if image!=target:shutil.copy2(image,target)
    a['reference_image']=str(target.relative_to(p))
    jwrite(p/'asset_manifest.json',manifest)
    client=Tripo(key)
    token=client.upload(target)
    # Record uploaded token before fee-bearing submit; no implicit retry on errors.
    a['upload_token']=token;a['status']='uploaded_pending_submit'
    jwrite(p/'asset_manifest.json',manifest)
    task_id=client.submit(token)
    a['task_id']=task_id;a['status']='generating'
    jwrite(p/'asset_manifest.json',manifest)
    print('TRIPO SUBMITTED',args.id,task_id,'(paid operation; do not resubmit)')

def download_url(url,dest):
    from urllib.parse import urlsplit
    if urlsplit(url).scheme!='https':raise ValueError('Model URL must be HTTPS')
    tmp=dest.with_suffix('.download')
    try:
        with request.urlopen(request.Request(url),timeout=70) as response, tmp.open('wb') as out:
            size=0
            while True:
                buf=response.read(65536)
                if not buf:break
                size+=len(buf)
                if size>150*1024*1024:raise ValueError('Model larger than 150MB')
                out.write(buf)
        glb_header(tmp)
        if dest.exists():raise ValueError('Destination asset already exists: no overwrite')
        tmp.replace(dest)
    finally:
        if tmp.exists():tmp.unlink()

def tripo_status(args):
    check_asset_id(args.id)
    p=rootproject(args.project);check_project(p)
    if jread(p/'project.json').get('execution_mode')!='live_tripo':
        raise ValueError('MOCK MODE ACTIVE: real Tripo status API disabled')
    manifest=jread(p/'asset_manifest.json')
    a=next((a for a in manifest['assets'] if a['asset_id']==args.id),None)
    if not a or not a.get('task_id'):raise ValueError('Asset has no submitted Tripo task')
    status=Tripo(get_key()).task(a['task_id'])
    state=status.get('status','unknown')
    print('TRIPO STATUS',a['task_id'],state,'progress',status.get('progress',None))
    if state=='success':
        model_url=status.get('output',{}).get('model_url')
        if not model_url:raise ValueError('Successful task missing model_url')
        dst=p/'assets'/(args.id+'.glb')
        if not dst.exists():download_url(model_url,dst)
        a['model_path']=str(dst.relative_to(p));a['status']='downloaded_unverified'
        a['credits_consumed']=status.get('credits_consumed')
    elif state in ('failed','cancelled','expired','banned'):
        a['status']='failed';a['last_error']=status.get('error_message','')
    elif state in ('queued','running'):
        a['status']='generating'
    else:
        a['status']='unknown';a['last_error']='Unknown status, do not resubmit'
    jwrite(p/'asset_manifest.json',manifest)

def main(argv=None):
    ap=argparse.ArgumentParser(description='Scene Builder v0.8 offline-first CLI')
    sub=ap.add_subparsers(dest='cmd',required=True)
    specs=[
      ('init',init,[('--project',True),('--name',False),('--reference',False),('--preset',False),('--force',False)]),
      ('styles',styles,[('--project',True)]),
      ('select-style',select_style,[('--project',True),('--id',True)]),
      ('compile',compile_scene,[('--project',True),('--render',False)]),
      ('run-blender',run_blender,[('--project',True),('--blender',True)]),
      ('status',status,[('--project',True)]),
      ('register-asset',register,[('--project',True),('--id',True),('--glb',True)]),
      ('finalize-asset',finalize,[('--project',True),('--id',True)]),
      ('prepare-tripo',prepare_tripo,[('--project',True),('--id',True)]),
      ('tripo-submit',tripo_submit,[('--project',True),('--id',True),('--image',True),('--confirm-paid',False),('--max-tasks',True)]),
      ('tripo-status',tripo_status,[('--project',True),('--id',True)])]
    for cmd,fn,opts in specs:
        sp=sub.add_parser(cmd);sp.set_defaults(fn=fn)
        for name,required in opts:
            if name in ('--force','--render','--confirm-paid'):sp.add_argument(name,action='store_true')
            elif name=='--preset':sp.add_argument(name,choices=['coastal','blank'],default='coastal')
            elif name=='--max-tasks':sp.add_argument(name,type=int,default=1)
            else:sp.add_argument(name,required=required)
    args=ap.parse_args(argv)
    try:args.fn(args)
    except (ValueError,RuntimeError,OSError) as e:
        print('ERROR:',e,file=sys.stderr);return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
