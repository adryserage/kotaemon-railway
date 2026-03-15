FROM ghcr.io/cinnamon/kotaemon:main-full

# Override launch.sh to skip Ollama (not needed — we use external LLM APIs)
COPY launch.sh /app/launch.sh
RUN chmod +x /app/launch.sh

# Copy custom env if present
COPY .env* /app/

# Patch flowsettings to allow Google model override via env vars
COPY patch_flowsettings.py /app/patch_flowsettings.py
RUN cat /app/patch_flowsettings.py >> /app/flowsettings.py

EXPOSE 7860

ENTRYPOINT ["bash", "/app/launch.sh"]
