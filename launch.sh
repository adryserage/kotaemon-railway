#!/bin/bash

# Set defaults — PORT is injected by Railway
GRADIO_SERVER_NAME="${GRADIO_SERVER_NAME:-0.0.0.0}"
GRADIO_SERVER_PORT="${PORT:-${GRADIO_SERVER_PORT:-7860}}"

export GRADIO_SERVER_NAME
export GRADIO_SERVER_PORT
export GR_FILE_ROOT_PATH="/app"

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
    # Railway mode: skip Ollama (use external LLM APIs instead)
    python app.py
fi
