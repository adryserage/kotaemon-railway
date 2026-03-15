"""
REST API endpoints for devis-preprocessor integration.
- /api/ingest: Accept ZIP of markdown files for indexing
- /api/chat: Query the RAG pipeline and return answers
- /api/health: Health check
"""

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

# Maximum total size of extracted ZIP contents (100 MB)
MAX_EXTRACT_SIZE = 100 * 1024 * 1024

# Maximum size of the uploaded compressed ZIP file (150 MB)
MAX_UPLOAD_SIZE = 150 * 1024 * 1024

# Maximum length of a single chat message / question (characters)
MAX_MESSAGE_LENGTH = 10_000

# Maximum number of history turns accepted in a chat request
MAX_HISTORY_TURNS = 50

# Optional API key for protecting ingest and chat endpoints.
# Set API_SECRET_KEY env var to enable authentication.
_API_SECRET_KEY = os.environ.get("API_SECRET_KEY")

# Will be set by app_with_api.py after the App is created
_ktem_app = None


def set_ktem_app(app):
    """Called by app_with_api.py to share the kotaemon App instance."""
    global _ktem_app
    _ktem_app = app


async def _verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Dependency that enforces API key auth when API_SECRET_KEY is configured."""
    if _API_SECRET_KEY and x_api_key != _API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _safe_doc_name(filename: str) -> str:
    """Return a filesystem-safe directory name derived from *filename*.

    Strips directory components, removes the expected ZIP suffixes, then
    replaces any character that is not alphanumeric, dash, underscore, or dot
    with an underscore.  Raises ValueError if the result is empty.
    """
    # Keep only the final component to prevent path traversal.
    base = Path(filename).name
    base = base.replace("_sections.zip", "").replace(".zip", "")
    sanitized = re.sub(r"[^\w\-.]", "_", base)
    if not sanitized:
        raise ValueError(f"Cannot derive a safe directory name from: {filename!r}")
    return sanitized


# --- Ingest endpoint ---


@router.post("/api/ingest")
async def ingest_files(
    file: UploadFile = File(...),
    _: None = Depends(_verify_api_key),
):
    """Accept a ZIP of markdown files and extract them for Kotaemon indexing."""
    if not file.filename or not file.filename.endswith(".zip"):
        return JSONResponse(
            status_code=400,
            content={"error": "Only ZIP files are accepted"},
        )

    try:
        doc_name = _safe_doc_name(file.filename)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid filename"},
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
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
            # Guard against zip-slip: reject any member whose resolved path
            # would escape target_dir.
            resolved_target = target_dir.resolve()
            total_size = 0
            for member in zf.infolist():
                member_path = (resolved_target / member.filename).resolve()
                if not member_path.is_relative_to(resolved_target):
                    return JSONResponse(
                        status_code=400,
                        content={"error": "ZIP contains invalid path entries"},
                    )
                # Guard against zip bombs.
                total_size += member.file_size
                if total_size > MAX_EXTRACT_SIZE:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "ZIP contents exceed maximum allowed size"},
                    )
            zf.extractall(target_dir)

        extracted_files = list(target_dir.rglob("*.md"))

        return {
            "status": "ok",
            "message": f"{len(extracted_files)} files extracted",
            "directory": str(target_dir),
            "files": [f.name for f in extracted_files],
        }
    except zipfile.BadZipFile:
        return JSONResponse(status_code=400, content={"error": "Invalid ZIP file"})
    except Exception:
        logger.exception("Unexpected error during ingest")
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
