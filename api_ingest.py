"""
REST API endpoints for devis-preprocessor integration.
- /api/ingest: Accept ZIP of markdown files for indexing
- /api/chat: Query the RAG pipeline and return answers
- /api/health: Health check
"""

import os
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

UPLOAD_DIR = Path(
    os.environ.get("KH_UPLOAD_DIR", "/app/ktem_app_data/user_data/files")
)

# Will be set by app_with_api.py after the App is created
_ktem_app = None


def set_ktem_app(app):
    """Called by app_with_api.py to share the kotaemon App instance."""
    global _ktem_app
    _ktem_app = app


# --- Ingest endpoint ---


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


# --- Chat endpoint ---


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    history: Optional[list[list[str]]] = None


class ChatResponse(BaseModel):
    answer: str
    references: str
    conversation_id: Optional[str] = None


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a question to the RAG pipeline and get an answer."""
    if _ktem_app is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Kotaemon app not initialized yet"},
        )

    try:
        from copy import deepcopy

        from ktem.pages.chat import ChatPage
        from ktem.reasoning import reasonings
        from kotaemon.base import Document

        # Get default settings
        settings = _ktem_app.default_settings.flatten()

        # Get the default reasoning class
        reasoning_mode = settings.get("reasoning.use", "simple")
        if reasoning_mode not in reasonings:
            reasoning_mode = list(reasonings.keys())[0]
        reasoning_cls = reasonings[reasoning_mode]
        reasoning_id = reasoning_cls.get_info()["id"]

        # Get all retrievers from all indices (search all indexed docs)
        retrievers = []
        for index in _ktem_app.index_manager.indices:
            iretrievers = index.get_retriever_pipelines(
                settings, "default", selected=[]
            )
            retrievers += iretrievers

        # Create the pipeline
        state = {"app": {}, reasoning_id: {}}
        pipeline = reasoning_cls.get_pipeline(settings, state, retrievers)

        # Run the pipeline
        history = req.history or []
        text = ""
        refs = ""

        for response in pipeline.stream(
            req.question, req.conversation_id or "", history
        ):
            if not isinstance(response, Document):
                continue
            if response.channel == "chat" and response.content:
                text += response.content
            elif response.channel == "info" and response.content:
                refs += response.content

        if not text:
            text = "Désolé, je n'ai pas trouvé de réponse dans les documents indexés."

        return ChatResponse(
            answer=text,
            references=refs,
            conversation_id=req.conversation_id,
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )


# --- Health endpoint ---


@router.get("/api/health")
async def health():
    return {"status": "ok", "app_ready": _ktem_app is not None}
