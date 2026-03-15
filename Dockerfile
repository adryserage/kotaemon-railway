FROM ghcr.io/cinnamon/kotaemon:main-full

# Override launch.sh to skip Ollama (not needed — we use external LLM APIs)
COPY launch.sh /app/launch.sh
RUN chmod +x /app/launch.sh

# Copy custom env if present
COPY .env* /app/

# Run as non-root user for security
RUN useradd -m -s /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

ENTRYPOINT ["bash", "/app/launch.sh"]
