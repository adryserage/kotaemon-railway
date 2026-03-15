"""Patch flowsettings to allow Google model names via environment variables.

Imported at the end of the default flowsettings.py to override hardcoded
model names with values from GOOGLE_CHAT_MODEL and GOOGLE_EMBEDDINGS_MODEL.
"""

import os
import re

_MODEL_NAME_RE = re.compile(r"^[\w\-./]+$")
_MODEL_NAME_MAX_LEN = 100


def _validated_model_name(env_var: str) -> str | None:
    """Return the env-var value only if it looks like a valid model name."""
    value = os.environ.get(env_var)
    if value:
        if len(value) > _MODEL_NAME_MAX_LEN:
            raise ValueError(
                f"Environment variable {env_var!r} value is too long (max {_MODEL_NAME_MAX_LEN} chars)"
            )
        if ".." in value or not _MODEL_NAME_RE.match(value):
            raise ValueError(
                f"Environment variable {env_var!r} contains an invalid model name: {value!r}"
            )
    return value


# Override Google Gemini chat model if env var is set
google_chat_model = _validated_model_name("GOOGLE_CHAT_MODEL")
if google_chat_model and "google" in KH_LLMS:  # noqa: F821
    KH_LLMS["google"]["spec"]["model_name"] = google_chat_model  # noqa: F821

# Override Google embedding model if env var is set
google_embeddings_model = _validated_model_name("GOOGLE_EMBEDDINGS_MODEL")
if google_embeddings_model and "google" in KH_EMBEDDINGS:  # noqa: F821
    KH_EMBEDDINGS["google"]["spec"]["model"] = google_embeddings_model  # noqa: F821
