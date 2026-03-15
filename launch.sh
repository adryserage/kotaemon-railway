#!/bin/bash

# Set defaults — PORT is injected by Railway
GRADIO_SERVER_NAME="${GRADIO_SERVER_NAME:-0.0.0.0}"
GRADIO_SERVER_PORT="${PORT:-${GRADIO_SERVER_PORT:-7860}}"

export GRADIO_SERVER_NAME
export GRADIO_SERVER_PORT
export GR_FILE_ROOT_PATH="/app"

# Ensure data directories are writable (Railway volumes may override permissions)
chmod -R 755 /app/ktem_app_data 2>/dev/null || true

if [ "$KH_DEMO_MODE" = "true" ]; then
    KH_FEATURE_USER_MANAGEMENT=false USE_LIGHTRAG=false \
    uvicorn sso_app_demo:app \
        --host "$GRADIO_SERVER_NAME" \
        --port "$GRADIO_SERVER_PORT"
elif [ "$KH_SSO_ENABLED" = "true" ]; then
    KH_SSO_ENABLED=true \
    uvicorn sso_app:app \
        --host "$GRADIO_SERVER_NAME" \
        --port "$GRADIO_SERVER_PORT"
else
    # Railway mode: skip Ollama, add /api/ingest endpoint
    python app_with_api.py
fi
