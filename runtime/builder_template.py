# Blender Scene Builder v0.6 — self-contained Blender runtime source.
# Used only inside Blender; generated/mcp_build.py is composed of CONFIG and this source.
import bpy, math, json, random, sys, traceback
from mathutils import Vector
from pathlib import Path

PROJECT = Path(CONFIG['project_dir']).resolve()
OUT = PROJECT / 'results'
OUT.mkdir(parents=True, exist_ok=True)
OWNER = CONFIG['project_id']
RNG = random.Random(CONFIG.get('seed', 2408))
ISSUES = []
REPORT = {'project_id': OWNER, 'objects_created': 0, 'imported_assets': [],
          'placeholders': [], 'warnings': ISSUES, 'finished': False}


def tag(ob, object_id):
    ob['sb_owner'] = OWNER
    ob['sb_object_id'] = object_id
    return ob


def collection(name):
    parent = bpy.data.collections.get('SB_' + OWNER)
    if parent is None:
        parent=bpy.data.collections.new('SB_' + OWNER)
        bpy.context.scene.collection.children.link(parent)
    cname='SB_' + OWNER+'_'+name
    coll=bpy.data.collections.get(cname)
    if coll is None:
        coll=bpy.data.collections.new(cname);parent.children.link(coll)
    return coll


def own_move(ob, coll):
    for c in list(ob.users_collection): c.objects.unlink(ob)
    coll.objects.link(ob)
    return ob


def clear_owned():
    # Mutates ONLY our own objects, never clears the entire scene.
    for ob in list(bpy.data.objects):
        if ob.get('sb_owner') == OWNER and not ob.get('sb_locked', False):
            bpy.data.objects.remove(ob, do_unlink=True)


def mat(name, color, metallic=0, roughness=0.7):
    name='SB_'+OWNER+'_MAT_'+name
    ma=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    ma.diffuse_color=(*color,1)
    ma.use_nodes=True
    shader=next((n for n in ma.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if shader:
        shader.inputs['Base Color'].default_value=(*color,1)
        shader.inputs['Metallic'].default_value=metallic
        shader.inputs['Roughness'].default_value=roughness
    return ma


def cube(object_id, name, loc, scale, material, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob=bpy.context.object;ob.name='SB_'+object_id
    ob.dimensions=scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material: ob.data.materials.append(material)
    tag(ob,object_id);own_move(ob,coll)
    REPORT['objects_created']+=1
    return ob


def ico(object_id, loc, size, material, coll, subdivisions=1):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions,radius=1,location=loc)
    ob=bpy.context.object;ob.name='SB_'+object_id
    ob.scale=size
    if material: ob.data.materials.append(material)
    tag(ob,object_id);own_move(ob,coll)
    REPORT['objects_created']+=1
    return ob


def linked_clone(source, object_id, loc, scale=(1,1,1)):
    ob=source.copy()  # shares source.data so this is a mesh-data instance
    for c in source.users_collection: c.objects.link(ob)
    ob.name='SB_'+object_id
    ob.location=loc; ob.scale=scale
    tag(ob,object_id)
    REPORT['objects_created']+=1
    return ob


def terrain_y(x):
    return -7.0 + 0.016*x*x  # curved shoreline / crescent bay


def land_height(x,y):
    d=y-terrain_y(x)
    if d < 0: return -0.16
    if d < 5: return 0.01 + .012*d
    upland=max(0,d-5)
    return 0.07 + 0.018*upland + 0.003*upland**2 + .16*math.sin(x*.14)*math.sin(y*.18)


def create_land(sand, grass):
    coll=collection('Terrain');nx=70;ny=60
    verts=[];faces=[];indices=[]
    for iy in range(ny+1):
        y=-26 + 57*iy/ny
        for ix in range(nx+1):
            x=-36 + 72*ix/nx
            verts.append((x,y,land_height(x,y)))
    for iy in range(ny):
        for ix in range(nx):
            a=iy*(nx+1)+ix
            faces.append((a,a+1,a+nx+2,a+nx+1))
            cx=-36+72*(ix+.5)/nx;cy=-26+57*(iy+.5)/ny
            indices.append(0 if cy-terrain_y(cx)<6.0 else 1)
    mesh=bpy.data.meshes.new('SB_TerrainMesh');mesh.from_pydata(verts,[],faces);mesh.update()
    ob=bpy.data.objects.new('SB_terrain',mesh);coll.objects.link(ob);tag(ob,'terrain')
    mesh.materials.append(sand);mesh.materials.append(grass)
    for poly,idx in zip(mesh.polygons,indices): poly.material_index=idx
    REPORT['objects_created']+=1


def create_water(material):
    coll=collection('Water')
    # A plane exists beneath the visual shader. A shader alone is not water geometry.
    water=cube('ocean','Ocean surface',(0,-21,-0.25),(110,48,.07),material,coll)
    ma=water.data.materials[0];nodes=ma.node_tree.nodes;links=ma.node_tree.links
    shader=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=6
    noise.inputs['Detail'].default_value=2
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.19
    bump.inputs['Distance'].default_value=.06
    links.new(noise.outputs['Fac'],bump.inputs['Height'])
    links.new(bump.outputs['Normal'],shader.inputs['Normal'])


def gable_roof(id, x, y, z, w, d, h, material, coll):
    # Real geometry rather than a painted triangular roof.
    verts=[(x-w/2,y-d/2,z),(x+w/2,y-d/2,z),(x+w/2,y+d/2,z),(x-w/2,y+d/2,z),
           (x,y-d/2,z+h),(x,y+d/2,z+h)]
    faces=[(0,1,4),(3,5,2),(0,4,5,3),(1,2,5,4)]
    mesh=bpy.data.meshes.new('SB_RoofMesh_'+id);mesh.from_pydata(verts,[],faces);mesh.update()
    ob=bpy.data.objects.new('SB_'+id,mesh);coll.objects.link(ob);tag(ob,id)
    mesh.materials.append(material);REPORT['objects_created']+=1


def build_house(house, mats):
    coll=collection('Architecture')
    hid=house['id'];x,y=house['xy'];w,d,h=house['size']
    z=land_height(x,y)
    body=cube(hid+'_wall','House',(x,y,z+h/2),(w,d,h),
             mats['yellow'] if house.get('color')=='yellow' else mats['white'],coll)
    gable_roof(hid+'_roof',x,y,z+h,w+.35,d+.5,h*.35,mats['tile'],coll)
    # Window/door proxies are **decorative only**, not cut-out openings.
    cube(hid+'_door','Door',(x,y-d/2-.035,z+.76),(.75,.09,1.52),mats['wood'],coll)
    for v in [-.29,.29]:
        cube(hid+'_window'+str(v),'Window',(x+w*v,y-d/2-.08,z+h*.58),(.48,.08,.61),mats['window'],coll)
    # No claims about actual Tripo mesh internal architecture.


def create_house_cluster(mats):
    houses=[
      {'id':'yellow_house','xy':(-24,10),'size':(7,7,5),'color':'yellow'},
      {'id':'white_left','xy':(-13,14),'size':(5,5,3.6)},
      {'id':'white_central','xy':(-1,16),'size':(4,4,3.4)},
      {'id':'white_right1','xy':(11,12),'size':(5,6,4.2)},
      {'id':'white_right2','xy':(20,15),'size':(6,5,4.6)},
      {'id':'white_right3','xy':(29,11),'size':(5,4,3.4)},
    ]
    for h in houses:build_house(h,mats)


def create_tree(id,x,y, trunk_mat, foliage_mat, coll):
    z=land_height(x,y);height=1.6+RNG.random()*1.7
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=.12, depth=height,location=(x,y,z+height/2))
    trunk=bpy.context.object;trunk.name='SB_'+id+'_trunk';trunk.data.materials.append(trunk_mat)
    own_move(trunk,coll);tag(trunk,id+'_trunk');REPORT['objects_created']+=1
    ico(id+'_crown',(x,y,z+height+1.05),(.9+RNG.random()*.6,.9+RNG.random()*.5,1.1),foliage_mat,coll,2)


def create_environment(mats):
    coll=collection('Vegetation')
    for i in range(18):
        x=RNG.uniform(-33,33);y=RNG.uniform(13,25)
        if (x < -20 and y<15) or (x>16 and y<17):continue
        create_tree('tree_'+str(i),x,y,mats['wood'],mats['foliage'],coll)
    # Re-use a single bush mesh with linked instances.
    source=ico('bush_source',(0,1000,0),(.62,.58,.45),mats['foliage'],coll,2)
    for i in range(34):
        x=RNG.uniform(-34,34);y=RNG.uniform(8,29)
        s=RNG.uniform(.65,1.3)
        linked_clone(source,'bush_'+str(i),(x,y,land_height(x,y)+.33*s),(s,s,s))
    rock_collection=collection('Rocks')
    source_rock=ico('rock_source',(0,1000,0),(.6,.5,.36),mats['rock'],rock_collection,1)
    for i in range(18):
        x=RNG.uniform(-33,33)
        y=terrain_y(x)+RNG.uniform(0,6)
        s=RNG.uniform(.5,1.8)
        linked_clone(source_rock,'rock_'+str(i),(x,y,land_height(x,y)+.25*s),(s,s,s))


def create_boat(id,x,y,mats):
    c=collection('Boats')
    body=cube(id+'_hull','Boat hull',(x,y,0.16),(3.7,1.3,.65),mats['boat'],c)
    cube(id+'_cabin','Boat cabin',(x+.1,y,.7),(1.2,.7,.8),mats['white'],c)
    cube(id+'_mast','Mast',(x-.3,y,1.35),(.11,.11,1.7),mats['wood'],c)


def imported_verts_world(ob):
    return [ob.matrix_world@Vector(v) for v in ob.bound_box]


def import_glb(spec):
    rel=spec.get('model_path')
    if not rel:return False
    src=(PROJECT/rel).resolve()
    if not src.is_relative_to(PROJECT) or not src.is_file():
        ISSUES.append('Asset missing/outside project: '+spec['asset_id']);return False
    bpy.ops.object.select_all(action='DESELECT')
    pre=set(bpy.data.objects)
    try:bpy.ops.import_scene.gltf(filepath=str(src))
    except Exception as ex:
        ISSUES.append('Failed GLB import '+spec['asset_id']+': '+str(ex));return False
    new=[ob for ob in bpy.data.objects if ob not in pre]
    meshes=[ob for ob in new if ob.type=='MESH']
    if not meshes:
        ISSUES.append('Imported asset has no mesh: '+spec['asset_id']);return False
    coll=collection('Imported')
    # Normalize the whole imported hierarchy with an empty parent, preserving child relationships.
    root=bpy.data.objects.new('SB_ASSET_'+spec['asset_id'],None);coll.objects.link(root)
    tag(root,'asset_root_'+spec['asset_id']);root['sb_asset_id']=spec['asset_id']
    root['sb_import_status']='imported_pending_review'
    top=[ob for ob in new if ob.parent not in new]
    for ob in top:
        matrix=ob.matrix_world.copy();ob.parent=root;ob.matrix_world=matrix
    bpy.context.view_layer.update()
    verts=[v for ob in meshes for v in imported_verts_world(ob)]
    mins=[min(v[k] for v in verts) for k in range(3)]
    maxs=[max(v[k] for v in verts) for k in range(3)]
    dims=[maxs[k]-mins[k] for k in range(3)]
    want=spec.get('dimensions') or [1,1,1]
    try: ratio=min(float(want[i])/max(float(dims[i]),1e-5) for i in range(3))
    except Exception:ratio=1
    root.scale=(ratio,ratio,ratio)
    bpy.context.view_layer.update()
    verts=[v for ob in meshes for v in imported_verts_world(ob)]
    mins=[min(v[k] for v in verts) for k in range(3)]
    maxs=[max(v[k] for v in verts) for k in range(3)]
    position=spec.get('placement') or [0,0,0]
    offset=Vector((float(position[0])-(mins[0]+maxs[0])/2,
                   float(position[1])-(mins[1]+maxs[1])/2,
                   float(position[2])-mins[2]))
    root.location+=offset
    bpy.context.view_layer.update()
    # Set the editable parent pivot to requested ground placement, preserving child world transforms.
    top_world={ob:ob.matrix_world.copy() for ob in top}
    root.location=Vector(position)
    bpy.context.view_layer.update()
    for ob,matrix in top_world.items():ob.matrix_world=matrix
    bpy.context.view_layer.update()
    for ob in new:tag(ob,'import_'+spec['asset_id']+'_'+ob.name)
    # Minimal refinement: a simple box collision proxy, not a precision collision mesh.
    if spec.get('refinement',{}).get('collision')=='box_proxy':
        verts=[v for ob in meshes for v in imported_verts_world(ob)]
        mins=[min(v[k] for v in verts) for k in range(3)]
        maxs=[max(v[k] for v in verts) for k in range(3)]
        center=tuple((mins[k]+maxs[k])/2 for k in range(3))
        extents=tuple(max(maxs[k]-mins[k],.01) for k in range(3))
        col=cube('collision_'+spec['asset_id'],'Box collision',center,extents,None,collection('Collision'))
        col.display_type='WIRE';col.hide_render=True
        col['sb_collision_approximation']='axis_aligned_box_only'
    REPORT['imported_assets'].append({'asset_id':spec['asset_id'],'status':'imported_pending_review',
                                     'mesh_count':len(meshes),'source':rel,
                                     'collision':'box_proxy' if spec.get('refinement',{}).get('collision')=='box_proxy' else 'none'})
    return True


def add_asset_fallback(spec,mats):
    asset_id=spec['asset_id']
    if import_glb(spec):return
    if not spec.get('use_placeholder',True):return
    pos=spec.get('placement') or [0,0,0]
    size=spec.get('dimensions') or [1,1,1]
    cube('proxy_'+asset_id,'Proxy',(pos[0],pos[1],pos[2]+size[2]/2),size,mats['proxy'],collection('Placeholders'))
    REPORT['placeholders'].append(asset_id)


def create_camera_and_light():
    camera_collection=collection('Cameras')
    camera=bpy.data.objects.get('SB_'+OWNER+'_camera')
    if camera is None:
        camera_data=bpy.data.cameras.new('SB_'+OWNER+'_camera')
        camera=bpy.data.objects.new('SB_'+OWNER+'_camera',camera_data)
        camera_collection.objects.link(camera);tag(camera,'camera');REPORT['objects_created']+=1
    cam=CONFIG.get('camera') or {}
    camera.location=cam.get('position',[40,-57,35]);target=Vector(cam.get('target',[0,4,2]))
    direction=target-Vector(camera.location)
    camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO' if cam.get('projection','ORTHO')=='ORTHO' else 'PERSP'
    if camera.data.type=='ORTHO':camera.data.ortho_scale=cam.get('ortho_scale',83)
    else:camera.data.lens=cam.get('lens_mm',30)
    bpy.context.scene.camera=camera
    c=collection('Lighting')
    if not any(ob.get('sb_object_id')=='sun' and ob.get('sb_owner')==OWNER for ob in bpy.data.objects):
        light=bpy.data.lights.new('SB_sun','SUN');light.energy=2.0
        ob=bpy.data.objects.new('SB_sun',light);c.objects.link(ob);tag(ob,'sun')
        ob.rotation_euler=(math.radians(30),math.radians(-25),math.radians(-25))
        REPORT['objects_created']+=1


def snapshot_and_save():
    out=OUT/'scene.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    REPORT['finished']=out.is_file()
    REPORT['blend_file']=str(out)
    REPORT['owned_objects']=sum(1 for ob in bpy.data.objects if ob.get('sb_owner')==OWNER)
    REPORT['mesh_objects']=sum(1 for ob in bpy.data.objects if ob.get('sb_owner')==OWNER and ob.type=='MESH')
    if CONFIG.get('render_preview',False):
        scene=bpy.context.scene
        try: scene.render.engine='BLENDER_EEVEE_NEXT'
        except (TypeError, ValueError, AttributeError): pass
        scene.render.resolution_x=960;scene.render.resolution_y=640;scene.render.resolution_percentage=100
        scene.render.filepath=str(OUT/'preview.png')
        try:bpy.ops.render.render(write_still=True)
        except Exception as ex:ISSUES.append('Preview render failed: '+str(ex))
    with (OUT/'blender_report.json').open('w',encoding='utf-8') as f:json.dump(REPORT,f,ensure_ascii=False,indent=2)
    print('SB_BUILD_REPORT='+json.dumps(REPORT,ensure_ascii=False))


def build():
    if bpy.data.filepath and not str(bpy.data.filepath).startswith(str(PROJECT)) and not CONFIG.get('allow_existing_scene',False):
        raise RuntimeError('Existing .blend outside project; cannot modify without explicit override')
    clear_owned()
    def rgb(hexstr):
        h=hexstr.lstrip('#')
        return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
    palettes=CONFIG.get('palette', ['#EACA8D','#66A2C2','#71B181'])
    # Selection affects output materials, not just JSON metadata.
    tone_sand,tone_water,tone_vegetation=[rgb(x) for x in palettes[:3]]
    mats={
      'sand':mat('sand',tone_sand), 'grass':mat('grass',tone_vegetation),
      'water':mat('water',tone_water,.1,.22),'yellow':mat('yellow',(.94,.69,.28)),
      'white':mat('white',(.87,.85,.74)),'tile':mat('roof',(.62,.27,.17)),
      'wood':mat('wood',(.36,.22,.12)), 'window':mat('window',(.18,.34,.42),.06,.28),
      'foliage':mat('foliage',tuple(v*.66 for v in tone_vegetation)),'rock':mat('rock',(.34,.38,.39)),
      'boat':mat('boat',(.7,.17,.12)),'proxy':mat('proxy',(.86,.3,.68))
    }
    create_land(mats['sand'],mats['grass'])
    create_water(mats['water'])
    create_house_cluster(mats)
    create_environment(mats)
    create_boat('boat_one',-5,-16,mats)
    create_boat('boat_two',13,-21,mats)
    for spec in CONFIG.get('assets',[]): add_asset_fallback(spec,mats)
    create_camera_and_light()
    snapshot_and_save()

build()
