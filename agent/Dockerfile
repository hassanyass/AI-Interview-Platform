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

# Run Agent
CMD ["./start.sh"]
