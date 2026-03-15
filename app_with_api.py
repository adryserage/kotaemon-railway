"""
Wrapper around Kotaemon's app.py that adds REST API endpoints.
Replaces `python app.py` in launch.sh.

Endpoints added:
- POST /api/ingest  — accept ZIP of markdown files
- POST /api/chat    — query the RAG pipeline
- GET  /api/health  — health check
"""

import os
import time

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
app = App()

# Share the app instance with the API so /api/chat can use the RAG pipeline
set_ktem_app(app)

# Build and launch the Gradio UI
demo = app.make()
demo.queue()

demo.launch(
    favicon_path=app._favicon,
    inbrowser=False,
    allowed_paths=[
        "libs/ktem/ktem/assets",
        GRADIO_TEMP_DIR,
    ],
    share=KH_GRADIO_SHARE,
    prevent_thread_lock=True,
)

# Mount the REST API onto Gradio's FastAPI server
demo.server.app.include_router(api_router)

print("API endpoints mounted: /api/ingest, /api/chat, /api/health")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
