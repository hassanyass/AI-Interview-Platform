FROM python:3.12-slim

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
