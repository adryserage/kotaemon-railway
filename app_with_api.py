"""
Wrapper around Kotaemon's app.py that adds the /api/ingest endpoint.
Replaces `python app.py` in launch.sh.
"""

import os

from theflow.settings import settings as flowsettings

KH_APP_DATA_DIR = getattr(flowsettings, "KH_APP_DATA_DIR", ".")
KH_GRADIO_SHARE = getattr(flowsettings, "KH_GRADIO_SHARE", False)
GRADIO_TEMP_DIR = os.getenv("GRADIO_TEMP_DIR", None)
if GRADIO_TEMP_DIR is None:
    GRADIO_TEMP_DIR = os.path.join(KH_APP_DATA_DIR, "gradio_tmp")
    os.environ["GRADIO_TEMP_DIR"] = GRADIO_TEMP_DIR

from ktem.main import App  # noqa: E402
from api_ingest import router as ingest_router  # noqa: E402

app = App()
demo = app.make()
demo.queue()

# Access the underlying FastAPI app and mount our API routes
fastapi_app = demo.launch(
    favicon_path=app._favicon,
    inbrowser=False,
    allowed_paths=[
        "libs/ktem/ktem/assets",
        GRADIO_TEMP_DIR,
    ],
    share=KH_GRADIO_SHARE,
    prevent_thread_lock=True,
)

# Mount the ingest API onto Gradio's FastAPI server
demo.server.app.include_router(ingest_router)

# Keep the process alive
import time

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
