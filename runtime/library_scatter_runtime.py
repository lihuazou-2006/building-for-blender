"""Run inside Blender only, with the target scene already loaded.

This is a test-scale Python linked-mesh scatter fallback, NOT Geometry Nodes.
Individual instances share mesh datablocks, conserving geometry memory but
still creating Blender objects. For huge forests use a tested GN scattering adapter.
"""
import bpy, random, json, hashlib
from pathlib import Path
from mathutils import Vector

PRJ=Path(CONFIG['project_dir']).resolve()
OWNER=CONFIG['project_id']
REPORT={'project_id':OWNER,'jobs':[],'warnings':[],'finished':False}


def owned(ob,kind):
    ob['sb_owner']=OWNER
    ob['sb_scatter_kind']=kind
    return ob


def coll(name):
    cname='SB_'+OWNER+'_'+name
    c=bpy.data.collections.get(cname)
    if c is None:
        c=bpy.data.collections.new(cname)
        bpy.context.scene.collection.children.link(c)
    return c


def ground_height(ground,x,y):
    inverse=ground.matrix_world.inverted()
    origin=inverse @ Vector((x,y,1000))
    direction=(ground.matrix_world.to_3x3().inverted() @ Vector((0,0,-1))).normalized()
    ok,point,normal,face=ground.ray_cast(origin,direction)
    return (ground.matrix_world @ point).z if ok else None


def import_source(aid,filepath):
    source_collection=coll('ScatterSource_'+aid)
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(filepath))
    added=[obj for obj in bpy.data.objects if obj not in before]
    meshes=[obj for obj in added if obj.type=='MESH']
    if not meshes:
        raise RuntimeError('GLB has no mesh: '+aid)
    # Normalize source hierarchy so bottom-center is at origin.
    bpy.context.view_layer.update()
    verts=[m.matrix_world @ Vector(corner) for m in meshes for corner in m.bound_box]
    center_x=(min(v.x for v in verts)+max(v.x for v in verts))/2
    center_y=(min(v.y for v in verts)+max(v.y for v in verts))/2
    bottom=min(v.z for v in verts)
    top=[o for o in added if o.parent not in added]
    root=bpy.data.objects.new('SBV08_SOURCE_'+aid,None)
    source_collection.objects.link(root);owned(root,'source')
    for ob in top:
        mat=ob.matrix_world.copy()
        ob.parent=root
        ob.matrix_world=mat
    root.location=(-center_x,-center_y,-bottom)
    bpy.context.view_layer.update()
    # Apply normalization to source children rather than leaving a hidden root transform.
    source_matrices={ob:ob.matrix_world.copy() for ob in top}
    root.location=(0,0,0)
    bpy.context.view_layer.update()
    for ob,mat in source_matrices.items():ob.matrix_world=mat
    bpy.context.view_layer.update()
    for ob in added:
        owned(ob,'source')
        for existing_coll in list(ob.users_collection): existing_coll.objects.unlink(ob)
        source_collection.objects.link(ob)
        ob.hide_render=True
    root.hide_render=True
    return root, added


def instantiate(source_root, originals, collection, aid, index, location, azimuth, scale):
    instance_root=bpy.data.objects.new('SBV08_'+aid+'_'+str(index),None)
    collection.objects.link(instance_root)
    owned(instance_root,'instance_root')
    instance_root['sb_asset_id']=aid
    clones={ob:ob.copy() for ob in originals}
    for old,new in clones.items():
        new.name='SBV08_'+aid+'_'+str(index)+'_'+old.name
        collection.objects.link(new)
        new.parent=instance_root if old.parent==source_root else clones.get(old.parent,instance_root)
        # retain the authored local transform relative to the source parent
        new.matrix_basis=old.matrix_basis.copy()
        new.matrix_parent_inverse=old.matrix_parent_inverse.copy()
        new.hide_render=False
        owned(new,'linked_instance')
    instance_root.location=location
    instance_root.rotation_euler.z=azimuth
    instance_root.scale=(scale,scale,scale)
    return instance_root


def scatter(job):
    aid=job['asset_id']
    ground=bpy.data.objects.get(job['surface_object'])
    if ground is None or ground.type!='MESH':
        raise RuntimeError('Ground surface missing or not mesh: '+job['surface_object'])
    target_coll=coll('ScatterInstances_'+aid)
    old=[o for o in target_coll.objects if o.get('sb_owner')==OWNER]
    if old:
        raise RuntimeError('Scatter already exists for '+aid+'; no destructive overwrite; use a fresh scene/checkpoint')
    filepath=(PRJ/job['model_path']).resolve()
    if not filepath.is_relative_to(PRJ) or not filepath.is_file():
        raise RuntimeError('Missing model or unsafe model path: '+aid)
    source_root, originals=import_source(aid,filepath)
    rng=random.Random(job['seed'])
    x0,x1,y0,y1=job['bounds_xy']
    used=0
    for i in range(job['count']):
        x=rng.uniform(x0,x1);y=rng.uniform(y0,y1)
        z=ground_height(ground,x,y)
        if z is None:
            REPORT['warnings'].append(f'{aid} point {i} missed surface')
            continue
        s=rng.uniform(job['scale_range'][0],job['scale_range'][1])
        instantiate(source_root,originals,target_coll,aid,i,(x,y,z),rng.uniform(0,6.283185307),s)
        used+=1
    REPORT['jobs'].append({'asset_id':aid,'requested':job['count'],'placed':used,
                           'surface':job['surface_object'],'source_model':job['model_path']})


def main():
    if bpy.data.filepath and not Path(bpy.data.filepath).resolve().is_relative_to(PRJ):
        raise RuntimeError('Refusing to change a scene saved outside this project')
    for job in CONFIG['jobs']:
        scatter(job)
    output=PRJ/'results'/'scatter_scene.blend'
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        raise RuntimeError('Scatter output already exists, refusing overwrite: '+str(output))
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    REPORT['finished']=True
    reportfile=PRJ/'results'/'scatter_report.json'
    reportfile.write_text(json.dumps(REPORT,indent=2,ensure_ascii=False),encoding='utf-8')
    print('SBV08_SCATTER_OK '+str(reportfile))

main()
