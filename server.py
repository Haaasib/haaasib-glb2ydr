from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import tempfile
import subprocess
import glob
import io
import zipfile
from pathlib import Path
import webbrowser

import webbrowser

current_conversion_status = "System Idle"

app = FastAPI()

@app.get("/status")
def get_status():
    return {"status": current_conversion_status}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "index.html"
BLENDER_EXE = os.environ.get(
    "BLENDER_EXE",
    r"C:\Program Files\Blender Foundation\Blender 4.5",
)
CONVERT_SCRIPT = str(BASE_DIR / "convert.py")


@app.get("/")
async def index():
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(str(INDEX_HTML), media_type="text/html")


@app.post("/convert")
async def convert_model(
    model: UploadFile = File(...),
    output_type: str = "raw",
    scale_height: float | None = Form(None),
    scale_unit: str = Form("m"),
    blender_exe: str | None = Form(None),
):
    if not (model.filename.lower().endswith(".glb") or model.filename.lower().endswith(".gltf")):
        raise HTTPException(status_code=400, detail="Only .glb/.gltf files are supported.")

    with tempfile.TemporaryDirectory(prefix="ydr_convert_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        glb_path = tmpdir_path / model.filename

        content = await model.read()
        glb_path.write_bytes(content)

        cache_root = tmpdir_path / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["GLB_PATH"] = str(glb_path)
        env["CACHE_ROOT"] = str(cache_root)
        if scale_height is not None:
            env["TARGET_HEIGHT"] = str(scale_height)
            env["TARGET_HEIGHT_UNIT"] = scale_unit
        exe_path = blender_exe or BLENDER_EXE

        if os.path.isdir(exe_path):
            exe_path = os.path.join(exe_path, "blender.exe")

        if not os.path.exists(exe_path):
            raise HTTPException(
                status_code=500,
                detail=f"Blender executable not found: {exe_path}. Set BLENDER_EXE env var or configure the path in the UI.",
            )

        import asyncio
        process = await asyncio.create_subprocess_exec(
            exe_path,
            "-b",
            "-P",
            CONVERT_SCRIPT,
            env=env,
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        global current_conversion_status
        current_conversion_status = "Starting Blender conversion..."

        log_path = BASE_DIR / "latest_blender_log.txt"
        last_status = ""
        with open(log_path, "w", encoding="utf-8") as log_f:
            log_f.write("=== BLENDER LOG ===\n")
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                log_f.write(line)
                log_f.flush()
                # If we see our custom status tag, update the global status
                if line.startswith("[STATUS] "):
                    s = line[len("[STATUS] ") :].strip()
                    last_status = s
                    current_conversion_status = s

        await process.wait()

        export_source_root = None

        req_dirs = [
            p for p in cache_root.iterdir()
            if p.is_dir() and p.name.startswith("req-")
        ]

        if req_dirs:
            export_source_root = max(req_dirs, key=lambda p: p.stat().st_mtime)

        if export_source_root is None or not any(export_source_root.rglob("*")):
            gen8_dir = BASE_DIR / "gen8"
            gen9_dir = BASE_DIR / "gen9"
            if not (gen8_dir.exists() or gen9_dir.exists()):
                return PlainTextResponse("No export files produced.", status_code=500)
            export_source_root = BASE_DIR

        normalized_type = output_type.lower()
        if normalized_type not in {"raw", "fivem"}:
            normalized_type = "raw"

        gen8_dir = export_source_root / "gen8"
        raw_root = gen8_dir if gen8_dir.exists() else export_source_root

        model_base = os.path.splitext(model.filename)[0]

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if normalized_type == "fivem":
                resource_name = f"haaasib-{model_base}"

                fxmanifest_content = """fx_version 'bodacious'
game 'gta5'
Author 'mfhasib'
version '1.0.0'
data_file 'DLC_ITYP_REQUEST' 'stream/*.ytyp'
files {
    'stream/*.ytyp',
}
lua54 'yes'
"""
                zf.writestr(f"{resource_name}/fxmanifest.lua", fxmanifest_content)

                search_root = raw_root
                for root, _, files in os.walk(search_root):
                    for name in files:
                        lower = name.lower()
                        if not (lower.endswith(".ydr") or lower.endswith(".ytyp")):
                            continue
                        full_path = os.path.join(root, name)
                        arcname = os.path.join(resource_name, "stream", name)
                        zf.write(full_path, arcname)
            else:
                for root, _, files in os.walk(raw_root):
                    for name in files:
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, raw_root)
                        zf.write(full_path, rel_path)

        buffer.seek(0)

        suffix = "_fivem.zip" if normalized_type == "fivem" else "_raw.zip"
        download_name = model_base + suffix

        headers = {
            "Content-Disposition": f'attachment; filename="{download_name}"'
        }
        if last_status:
            headers["X-Converter-Status"] = last_status

        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers=headers,
        )


if __name__ == "__main__":
    url = "http://127.0.0.1:8000"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run(app, host="127.0.0.1", port=8000)

