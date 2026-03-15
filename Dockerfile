FROM ghcr.io/cinnamon/kotaemon:main-full

# Override launch.sh to skip Ollama (not needed — we use external LLM APIs)
COPY launch.sh /app/launch.sh
RUN chmod +x /app/launch.sh

# Copy custom env if present
COPY .env* /app/

# Patch flowsettings to allow Google model override via env vars
COPY patch_flowsettings.py /app/patch_flowsettings.py
RUN cat /app/patch_flowsettings.py >> /app/flowsettings.py

# Pre-create data directories and set permissions for non-root user
RUN mkdir -p /app/ktem_app_data/changelogs /app/ktem_app_data/user_data \
    /app/ktem_app_data/markdown_cache_dir /app/ktem_app_data/chunks_cache_dir \
    /app/ktem_app_data/zip_cache_dir /app/ktem_app_data/zip_cache_dir_in \
    /app/ktem_app_data/huggingface \
    && useradd -m -s /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 7860

ENTRYPOINT ["bash", "/app/launch.sh"]
