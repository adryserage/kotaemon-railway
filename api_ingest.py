"""
REST API endpoint for ingesting documents into Kotaemon from devis-preprocessor.
Mounted alongside the Gradio app via app_with_api.py.
"""

import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

UPLOAD_DIR = Path(
    os.environ.get("KH_UPLOAD_DIR", "/app/ktem_app_data/user_data/files")
)


@router.post("/api/ingest")
async def ingest_files(file: UploadFile = File(...)):
    """Accept a ZIP of markdown files and extract them for Kotaemon indexing."""
    if not file.filename or not file.filename.endswith(".zip"):
        return JSONResponse(
            status_code=400,
            content={"error": "Only ZIP files are accepted"},
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        doc_name = file.filename.replace("_sections.zip", "").replace(".zip", "")
        target_dir = UPLOAD_DIR / doc_name
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(target_dir)

        extracted_files = list(target_dir.rglob("*.md"))

        return {
            "status": "ok",
            "message": f"{len(extracted_files)} fichiers extraits",
            "directory": str(target_dir),
            "files": [f.name for f in extracted_files],
        }
    except zipfile.BadZipFile:
        return JSONResponse(status_code=400, content={"error": "Invalid ZIP file"})
    finally:
        os.unlink(tmp_path)


@router.get("/api/health")
async def health():
    return {"status": "ok"}
