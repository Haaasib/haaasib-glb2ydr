import bpy
import addon_utils
import urllib.request
import os

addon_module = "material_combiner"
addon_zip_path = os.path.join(os.getcwd(), "material_combiner.zip")

download_url = "https://github.com/Grim-es/material-combiner-addon/archive/refs/heads/master.zip"

enabled, loaded = addon_utils.check(addon_module)

if not enabled:

    print("Material Combiner not installed. Downloading...")

    if not os.path.exists(addon_zip_path):
        urllib.request.urlretrieve(download_url, addon_zip_path)

    print("Installing addon...")

    bpy.ops.preferences.addon_install(
        filepath=addon_zip_path,
        overwrite=True
    )

    bpy.ops.preferences.addon_enable(module=addon_module)

    bpy.ops.wm.save_userpref()

    print("Material Combiner installed and enabled")

else:
    print("Material Combiner already installed")