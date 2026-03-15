"""
Wrapper around Kotaemon's app.py that adds REST API endpoints.
Replaces `python app.py` in launch.sh.

Uses gr.mount_gradio_app() — the official Gradio 4.x pattern for
combining FastAPI routes with a Gradio UI.

Endpoints added:
- POST /api/ingest  — accept ZIP of markdown files
- POST /api/chat    — query the RAG pipeline
- GET  /api/health  — health check
"""

import os

import gradio as gr
import uvicorn
from fastapi import FastAPI
from theflow.settings import settings as flowsettings

KH_APP_DATA_DIR = getattr(flowsettings, "KH_APP_DATA_DIR", ".")
KH_GRADIO_SHARE = getattr(flowsettings, "KH_GRADIO_SHARE", False)
GRADIO_TEMP_DIR = os.getenv("GRADIO_TEMP_DIR", None)
if GRADIO_TEMP_DIR is None:
    GRADIO_TEMP_DIR = os.path.join(KH_APP_DATA_DIR, "gradio_tmp")
    os.environ["GRADIO_TEMP_DIR"] = GRADIO_TEMP_DIR

from ktem.main import App  # noqa: E402
from api_ingest import router as api_router, set_ktem_app  # noqa: E402

# Create the kotaemon app
ktem_app = App()

# Share the app instance with the API so /api/chat can use the RAG pipeline
set_ktem_app(ktem_app)

# Build the Gradio UI
demo = ktem_app.make()
demo.queue()

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

print("API endpoints mounted: /api/ingest, /api/chat, /api/health")

# Run with uvicorn
host = os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0")
port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
uvicorn.run(fastapi_app, host=host, port=port)
