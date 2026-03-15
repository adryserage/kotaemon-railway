"""
REST API endpoints for devis-preprocessor integration.
- /api/ingest: Accept markdown files (JSON) and index into vector store
- /api/ingest/upload: Accept ZIP file upload and index into vector store
- /api/chat: Query the RAG pipeline and return answers
- /api/health: Health check
"""

import hmac
import logging
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path(
    os.environ.get("KH_UPLOAD_DIR", "/app/ktem_app_data/user_data/files")
)

MAX_MESSAGE_LENGTH = 10_000
MAX_HISTORY_TURNS = 50
MAX_INGEST_FILES = 200
MAX_FILE_CONTENT = 500_000
MAX_EXTRACT_SIZE = 100 * 1024 * 1024
MAX_UPLOAD_SIZE = 150 * 1024 * 1024

_API_SECRET_KEY = os.environ.get("API_SECRET_KEY")

# Will be set by app_with_api.py after the App is created
_ktem_app = None


def set_ktem_app(app):
    """Called by app_with_api.py to share the kotaemon App instance."""
    global _ktem_app
    _ktem_app = app


async def _verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Dependency that enforces API key auth when API_SECRET_KEY is configured."""
    if _API_SECRET_KEY:
        if not x_api_key or not hmac.compare_digest(x_api_key, _API_SECRET_KEY):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _safe_name(name: str) -> str:
    """Return a filesystem-safe name. Raises ValueError if result is empty."""
    base = Path(name).name
    sanitized = re.sub(r"[^\w\-.]", "_", base).strip(".")
    if not sanitized or sanitized == "..":
        raise ValueError(f"Cannot derive a safe name from: {name!r}")
    return sanitized


def _index_files(file_paths: list[str]) -> dict:
    """Run file paths through kotaemon's indexing pipeline. Returns result dict."""
    indexed_count = 0
    index_errors = []

    if not _ktem_app or not file_paths:
        return {"indexed": 0, "index_errors": ["App not ready or no files"]}

    try:
        index = _ktem_app.index_manager.indices[0]
        settings = _ktem_app.default_settings.flatten()
        indexing_pipeline = index.get_indexing_pipeline(settings, user_id=1)

        for response in indexing_pipeline.stream(file_paths, reindex=False):
            if hasattr(response, "content") and isinstance(response.content, dict):
                status = response.content.get("status")
                fname = response.content.get("file_name", "")
                if status == "success":
                    indexed_count += 1
                elif status == "failed":
                    msg = response.content.get("message", "unknown")
                    index_errors.append(f"{fname}: {msg}")
                    logger.warning("Index failed for %s: %s", fname, msg)
    except Exception:
        logger.exception("Error during indexing pipeline")
        index_errors.append("Indexing pipeline error (see server logs)")

    return {"indexed": indexed_count, "index_errors": index_errors}


# --- Ingest endpoint (JSON — direct markdown files) ---


class IngestFile(BaseModel):
    name: str = Field(..., max_length=255)
    content: str = Field(..., max_length=MAX_FILE_CONTENT)


class IngestRequest(BaseModel):
    doc_name: str = Field(..., max_length=255)
    files: list[IngestFile] = Field(..., max_length=MAX_INGEST_FILES)


@router.post("/api/ingest")
async def ingest_json(
    req: IngestRequest,
    _: None = Depends(_verify_api_key),
):
    """Accept markdown files as JSON and index them into the vector store."""
    if _ktem_app is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Kotaemon app not initialized yet"},
        )

    if not req.files:
        return JSONResponse(status_code=400, content={"error": "No files provided"})

    try:
        doc_name = _safe_name(req.doc_name)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid doc_name"})

    target_dir = UPLOAD_DIR / doc_name
    target_dir.mkdir(parents=True, exist_ok=True)

    written_files = []
    try:
        for f in req.files:
            try:
                safe_fname = _safe_name(f.name)
            except ValueError:
                logger.warning("Skipping file with invalid name: %s", f.name)
                continue
            file_path = target_dir / safe_fname
            file_path.write_text(f.content, encoding="utf-8")
            written_files.append(str(file_path))

        result = _index_files(written_files)

        return {
            "status": "ok",
            "message": f"{len(written_files)} files received, {result['indexed']} indexed",
            "indexed": result["indexed"],
            "total_files": len(written_files),
            **({"index_errors": result["index_errors"]} if result["index_errors"] else {}),
        }

    except Exception:
        logger.exception("Unexpected error during ingest")
        return JSONResponse(
            status_code=500, content={"error": "Internal server error"}
        )


# --- Ingest upload endpoint (ZIP file) ---


@router.post("/api/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    _: None = Depends(_verify_api_key),
):
    """Accept a ZIP of files, extract, and index into the vector store."""
    if _ktem_app is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Kotaemon app not initialized yet"},
        )

    if not file.filename or not file.filename.endswith(".zip"):
        return JSONResponse(
            status_code=400, content={"error": "Only ZIP files are accepted"}
        )

    try:
        doc_name = _safe_name(
            file.filename.replace("_sections.zip", "").replace(".zip", "")
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})

    target_dir = UPLOAD_DIR / doc_name
    tmp_path = None

    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": "Uploaded file exceeds maximum allowed size"},
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            resolved_target = target_dir.resolve()
            total_size = 0
            for member in zf.infolist():
                member_path = (resolved_target / member.filename).resolve()
                if not member_path.is_relative_to(resolved_target):
                    return JSONResponse(
                        status_code=400,
                        content={"error": "ZIP contains invalid path entries"},
                    )
                total_size += member.file_size
                if total_size > MAX_EXTRACT_SIZE:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "ZIP contents exceed maximum allowed size"},
                    )
            zf.extractall(target_dir)

        extracted_files = [str(f) for f in target_dir.rglob("*") if f.is_file()]
        result = _index_files(extracted_files)

        return {
            "status": "ok",
            "message": f"{len(extracted_files)} files extracted, {result['indexed']} indexed",
            "indexed": result["indexed"],
            "total_files": len(extracted_files),
            **({"index_errors": result["index_errors"]} if result["index_errors"] else {}),
        }

    except zipfile.BadZipFile:
        return JSONResponse(status_code=400, content={"error": "Invalid ZIP file"})
    except Exception:
        logger.exception("Unexpected error during ingest upload")
        return JSONResponse(
            status_code=500, content={"error": "Internal server error"}
        )
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("Failed to delete temporary file %s", tmp_path)


# --- Chat endpoint ---


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    conversation_id: Optional[str] = Field(None, max_length=200)
    history: Optional[list[list[str]]] = Field(None, max_length=MAX_HISTORY_TURNS)

    @field_validator("history")
    @classmethod
    def validate_history(cls, v):
        if v is None:
            return v
        for pair in v:
            if len(pair) != 2:
                raise ValueError("Each history entry must be [question, answer]")
            for msg in pair:
                if not isinstance(msg, str) or len(msg) > MAX_MESSAGE_LENGTH:
                    raise ValueError(
                        f"History messages must be strings ≤ {MAX_MESSAGE_LENGTH:,} chars"
                    )
        return v


class ChatResponse(BaseModel):
    answer: str
    references: str
    conversation_id: Optional[str] = None


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _: None = Depends(_verify_api_key),
):
    """Send a question to the RAG pipeline and get an answer."""
    if _ktem_app is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Kotaemon app not initialized yet"},
        )

    try:
        from ktem.components import reasonings
        from kotaemon.base import Document

        settings = _ktem_app.default_settings.flatten()

        reasoning_mode = settings.get("reasoning.use", "simple")
        if reasoning_mode not in reasonings:
            reasoning_mode = list(reasonings.keys())[0]
        reasoning_cls = reasonings[reasoning_mode]
        reasoning_id = reasoning_cls.get_info()["id"]

        retrievers = []
        for index in _ktem_app.index_manager.indices:
            iretrievers = index.get_retriever_pipelines(
                settings, 1, selected=["all", [], 1]
            )
            retrievers += iretrievers

        state = {"app": {}, reasoning_id: {}}
        pipeline = reasoning_cls.get_pipeline(settings, state, retrievers)

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

    except Exception:
        logger.exception("Unexpected error during chat")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )


# --- Health endpoint ---


@router.get("/api/health")
async def health():
    return {"status": "ok", "app_ready": _ktem_app is not None}
