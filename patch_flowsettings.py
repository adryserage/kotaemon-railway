"""Patch flowsettings to allow Google model names via environment variables.

Imported at the end of the default flowsettings.py to override hardcoded
model names with values from GOOGLE_CHAT_MODEL and GOOGLE_EMBEDDINGS_MODEL.
"""

import os

# Override Google Gemini chat model if env var is set
google_chat_model = os.environ.get("GOOGLE_CHAT_MODEL")
if google_chat_model and "google" in KH_LLMS:  # noqa: F821
    KH_LLMS["google"]["spec"]["model_name"] = google_chat_model  # noqa: F821

# Override Google embedding model if env var is set
google_embeddings_model = os.environ.get("GOOGLE_EMBEDDINGS_MODEL")
if google_embeddings_model and "google" in KH_EMBEDDINGS:  # noqa: F821
    KH_EMBEDDINGS["google"]["spec"]["model"] = google_embeddings_model  # noqa: F821
