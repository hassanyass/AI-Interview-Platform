FROM python:3.13-slim
# Aligned to 3.13 (2026-09-03), same reasoning as backend/Dockerfile: the
# local dev environment this project has actually been run and verified
# against all session is 3.13.5.

WORKDIR /app

# Install system dependencies required for audio processing (LiveKit/Silero)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

COPY start.sh .
RUN chmod +x start.sh

# H5-C: not root. Unlike the backend this process does write to disk --
# the Groq key-rotation state and the TTS cache live under
# AGENT_STATE_DIR -- so the directory is created and owned here. A Docker
# named volume mounted over it inherits this ownership only when the
# volume is NEW; a volume created by an earlier root-running image keeps
# root's ownership and the agent will fail to write to it. Recreate it
# (`docker volume rm <project>_agent_state`) when upgrading -- both the
# cache and the rotation index rebuild themselves. See
# docs/handover/runbooks/start-stop-upgrade.md.
ENV AGENT_STATE_DIR=/var/lib/himma-agent
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /var/lib/himma-agent \
    && chown -R app:app /app /var/lib/himma-agent
USER app

# No HEALTHCHECK on purpose: this is a LiveKit worker, not an HTTP
# service. It binds no port, and LiveKit does not probe one -- a
# healthcheck here could only test something that is not how the worker
# proves it is alive (it registers with LiveKit and renews session
# leases; see docs/handover/observability.md).

# Run Agent
CMD ["./start.sh"]
