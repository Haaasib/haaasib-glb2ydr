import bpy
import os
import subprocess
import shutil

glb_path = os.environ.get("GLB_PATH")

if not glb_path:
    raise FileNotFoundError("GLB_PATH environment variable is not set.")

model_name = os.path.splitext(os.path.basename(glb_path))[0]

script_root = os.path.dirname(__file__)
default_cache_root = os.path.join(script_root, "cache")
cache_root = os.environ.get("CACHE_ROOT", default_cache_root)
os.makedirs(cache_root, exist_ok=True)

existing_req_dirs = [
    d for d in os.listdir(cache_root)
    if os.path.isdir(os.path.join(cache_root, d)) and d.startswith("req-")
]

next_index = 1
if existing_req_dirs:
    numbers = []
    for name in existing_req_dirs:
        try:
            numbers.append(int(name.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    if numbers:
        next_index = max(numbers) + 1

export_root = os.path.join(cache_root, f"req-{next_index}")
os.makedirs(export_root, exist_ok=True)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


if not os.path.exists(glb_path):
    raise FileNotFoundError(f"GLB file not found: {glb_path}")

print("=== HAAASIB CONVERTER START ===")
print(f"GLB path: {glb_path}")

bpy.ops.import_scene.gltf(filepath=glb_path)

scene_objects = list(bpy.context.scene.objects)
print(f"Scene now has {len(scene_objects)} objects:")
for obj in scene_objects:
    print(f"  - {obj.name} (type={obj.type}, parent={obj.parent.name if obj.parent else 'None'})")

imported_meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
print(f"Imported selected meshes: {[o.name for o in imported_meshes]}")

if imported_meshes:
    main_obj = imported_meshes[0]
    print(f"Main mesh chosen: {main_obj.name}")
    main_obj.name = model_name
    if getattr(main_obj, "data", None) and hasattr(main_obj.data, "name"):
        main_obj.data.name = model_name

    # Optional rescale based on requested target height/size
    target_height_str = os.environ.get("TARGET_HEIGHT")
    target_unit = os.environ.get("TARGET_HEIGHT_UNIT", "m").lower()
    if target_height_str:
        try:
            target_height = float(target_height_str)
            if target_height > 0:
                if target_unit in ("ft", "feet"):
                    target_height_m = target_height * 0.3048
                else:
                    target_height_m = target_height

                bb = main_obj.bound_box
                xs = [v[0] for v in bb]
                ys = [v[1] for v in bb]
                zs = [v[2] for v in bb]
                size_x = max(xs) - min(xs)
                size_y = max(ys) - min(ys)
                size_z = max(zs) - min(zs)
                current_size = max(size_x, size_y, size_z)

                if current_size > 0:
                    scale_factor = target_height_m / current_size
                    print(
                        f"Rescaling main mesh from size {current_size:.4f} to "
                        f"{target_height_m:.4f} meters (factor {scale_factor:.4f})"
                    )
                    main_obj.scale[0] *= scale_factor
                    main_obj.scale[1] *= scale_factor
                    main_obj.scale[2] *= scale_factor
                else:
                    print("Current mesh size is zero, skipping rescale.")
        except ValueError:
            print(f"Invalid TARGET_HEIGHT '{target_height_str}', skipping rescale.")

    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)

    removed = 0
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        if obj is main_obj:
            continue
        print(f"Removing extra mesh: {obj.name}")
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    print(f"Removed {removed} extra mesh object(s), only main mesh kept.")

for obj in bpy.context.scene.objects:
    if obj.type != "MESH":
        continue

    for mat in obj.data.materials:
        if not mat or not mat.use_nodes:
            continue

        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:

                img = node.image
                base_name = os.path.splitext(img.name)[0]

                png_path = os.path.join(cache_root, base_name + ".png")
                dds_path = os.path.join(cache_root, base_name + ".dds")

                img.filepath_raw = png_path
                img.file_format = 'PNG'
                img.save()

                subprocess.run([
                    "texconv",
                    "-f", "BC7_UNORM",
                    "-y",
                    "-w", "2048",
                    "-h", "2048",
                    "-o", cache_root,
                    png_path
                ], check=True)

                if os.path.exists(png_path):
                    os.remove(png_path)

                if os.path.exists(dds_path):
                    dds_img = bpy.data.images.load(dds_path)
                    node.image = dds_img

bpy.context.scene.auto_create_embedded_col = True

bpy.ops.object.select_all(action='DESELECT')
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]

for obj in meshes:
    obj.select_set(True)

if meshes:
    bpy.context.view_layer.objects.active = meshes[0]

bpy.ops.sollumz.converttodrawable()

poly_mesh = None
for obj in bpy.context.scene.objects:
    if obj.name.endswith(".poly_mesh"):
        poly_mesh = obj
        break

if poly_mesh:
    bpy.ops.object.select_all(action='DESELECT')
    poly_mesh.select_set(True)
    bpy.context.view_layer.objects.active = poly_mesh

    while len(poly_mesh.material_slots) > 0:
        bpy.ops.object.material_slot_remove()

    bpy.data.window_managers["WinMan"].sz_collision_material_index = 1
    bpy.ops.sollumz.createcollisionmaterial()
    bpy.ops.sollumz.load_flag_preset()

bpy.ops.object.select_all(action='DESELECT')
mesh_objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]

for obj in mesh_objects:
    obj.select_set(True)

if mesh_objects:
    bpy.context.view_layer.objects.active = mesh_objects[0]

bpy.ops.sollumz.convert_active_material_to_selected()
bpy.ops.sollumz.setallmatembedded()
bpy.ops.sollumz.uv_maps_rename_by_order()
bpy.ops.sollumz.color_attrs_add_missing()

# Debug: list Sollumz types after conversion
print("Sollumz object types after conversion:")
for obj in bpy.context.scene.objects:
    stype = getattr(obj, "sollum_type", None)
    if stype:
        print(f"  - {obj.name}: sollum_type={stype}")

# Rename drawable objects without touching Sollumz's selection
drawable_types = {"sollumz_drawable", "sollumz_drawable_model"}
for obj in bpy.context.scene.objects:
    stype = getattr(obj, "sollum_type", "")
    if stype not in drawable_types:
        continue

    if stype == "sollumz_drawable":
        print(f"Renaming drawable '{obj.name}' to '{model_name}'")
        obj.name = model_name
    elif stype == "sollumz_drawable_model":
        print(f"Renaming drawable model '{obj.name}' to '{model_name}.model'")
        obj.name = f"{model_name}.model"

    if getattr(obj, "data", None) and hasattr(obj.data, "name"):
        obj.data.name = obj.name

bpy.context.scene.sollumz_export_path = export_root

print("Calling Sollumz export_assets with Sollumz's own selection.")
bpy.ops.sollumz.export_assets()

for folder_name in ("gen8", "gen9"):
    src = os.path.join(script_root, folder_name)
    if os.path.exists(src):
        dest = os.path.join(export_root, folder_name)

        if not os.path.exists(dest):
            shutil.move(src, dest)
        else:
            for root, dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                target_root = os.path.join(dest, rel)
                os.makedirs(target_root, exist_ok=True)
                for f in files:
                    shutil.move(
                        os.path.join(root, f),
                        os.path.join(target_root, f),
                    )
            shutil.rmtree(src, ignore_errors=True)

gen9_export = os.path.join(export_root, "gen9")
if os.path.exists(gen9_export):
    shutil.rmtree(gen9_export, ignore_errors=True)

dds_name = model_name
for root, dirs, files in os.walk(export_root):
    for f in files:
        if f.lower().endswith(".dds"):
            dds_name = os.path.splitext(f)[0]
            break
    if dds_name != model_name:
        break

gen8_export = os.path.join(export_root, "gen8")
os.makedirs(gen8_export, exist_ok=True)

ytyp_path = os.path.join(gen8_export, f"{model_name}.ytyp")

ytyp_content = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<CMapTypes>
  <extensions/>
  <archetypes>
    <Item type="CBaseArchetypeDef">
      <lodDist value="200.00000000"/>
      <flags value="32"/>
      <specialAttribute value="0"/>
      <bbMin x="-0.42132190" y="-0.32018530" z="0.00000000"/>
      <bbMax x="0.42026740" y="0.32077170" z="0.30480010"/>
      <bsCentre x="-0.00052725" y="0.00029323" z="0.15240000"/>
      <bsRadius value="0.55045470"/>
      <hdTextureDist value="100.00000000"/>
      <name>{model_name}</name>
      <textureDictionary>{dds_name}</textureDictionary>
      <clipDictionary/>
      <drawableDictionary/>
      <physicsDictionary>{model_name}</physicsDictionary>
      <assetType>ASSET_TYPE_DRAWABLE</assetType>
      <assetName>{model_name}</assetName>
      <extensions/>
    </Item>
  </archetypes>
  <name>{model_name}</name>
  <dependencies/>
  <compositeEntityTypes/>
</CMapTypes>
'''

with open(ytyp_path, "w", encoding="utf-8") as f:
    f.write(ytyp_content)