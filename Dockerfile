FROM ghcr.io/cinnamon/kotaemon:main-full

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
    CMD curl -f http://localhost:7860/api/health || exit 1

ENTRYPOINT ["bash", "/app/launch.sh"]
