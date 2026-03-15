FROM ghcr.io/cinnamon/kotaemon:main-full

# Upgrade Google AI packages (support gemini-embedding-2-preview etc.)
# Pins respect: langchain-google-genai 1.x needs google-generativeai <0.8,
# gradio-client needs websockets <12, opentelemetry needs protobuf <5.
RUN pip install --no-cache-dir --upgrade \
    "langchain-google-genai>=1.0.10,<2.0.0" \
    "google-generativeai>=0.7.0,<0.8.0" \
    "google-ai-generativelanguage>=0.6.10,<0.7.0" \
    "google-api-core>=2.24,<3.0" \
    "protobuf>=4.21,<5.0"

# Override launch.sh to skip Ollama (not needed — we use external LLM APIs)
COPY launch.sh /app/launch.sh
RUN chmod +x /app/launch.sh

# Patch flowsettings to allow Google model override via env vars
COPY patch_flowsettings.py /app/patch_flowsettings.py
RUN cat /app/patch_flowsettings.py >> /app/flowsettings.py

# Add ingest API for devis-preprocessor integration
COPY api_ingest.py /app/api_ingest.py
COPY app_with_api.py /app/app_with_api.py

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-7860}/api/health || exit 1

# NOTE: Running as root is required because Railway mounts volumes as
# root-owned at runtime. A non-root USER causes PermissionError on
# /app/ktem_app_data. The base image (kotaemon:main-full) is also
# designed to run as root.
ENTRYPOINT ["bash", "/app/launch.sh"]
