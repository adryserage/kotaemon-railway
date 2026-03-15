"""
Wrapper around Kotaemon's app.py that adds REST API endpoints.
Replaces `python app.py` in launch.sh.

Uses gr.mount_gradio_app() — the official Gradio 4.x pattern for
combining FastAPI routes with a Gradio UI.

Endpoints added:
- POST /api/ingest        — accept markdown files as JSON and index
- POST /api/ingest/upload — accept ZIP file upload and index
- POST /api/chat          — query the RAG pipeline
- GET  /api/health        — health check
"""

import logging
import os

import gradio as gr
import uvicorn
from fastapi import FastAPI
from theflow.settings import settings as flowsettings

logger = logging.getLogger(__name__)

KH_APP_DATA_DIR = getattr(flowsettings, "KH_APP_DATA_DIR", ".")
KH_GRADIO_SHARE = getattr(flowsettings, "KH_GRADIO_SHARE", False)
GRADIO_TEMP_DIR = os.getenv("GRADIO_TEMP_DIR", None)
if GRADIO_TEMP_DIR is None:
    GRADIO_TEMP_DIR = os.path.join(KH_APP_DATA_DIR, "gradio_tmp")
    os.environ["GRADIO_TEMP_DIR"] = GRADIO_TEMP_DIR

os.makedirs(GRADIO_TEMP_DIR, exist_ok=True)

from ktem.main import App  # noqa: E402
from api_ingest import router as api_router, set_ktem_app  # noqa: E402

# Create the kotaemon app
try:
    ktem_app = App()
    set_ktem_app(ktem_app)
    demo = ktem_app.make()
    demo.queue()
except Exception:
    logger.exception("Failed to initialise Kotaemon app — aborting startup")
    raise

# Create FastAPI app with API routes
fastapi_app = FastAPI()
fastapi_app.include_router(api_router)

# Mount Gradio onto FastAPI at root
gr.mount_gradio_app(
    fastapi_app,
    demo,
    path="/",
    allowed_paths=[
        "libs/ktem/ktem/assets",
        GRADIO_TEMP_DIR,
    ],
)

print("API endpoints mounted: /api/ingest, /api/ingest/upload, /api/chat, /api/health")

# Run with uvicorn
host = os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0")
port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
uvicorn.run(fastapi_app, host=host, port=port)
