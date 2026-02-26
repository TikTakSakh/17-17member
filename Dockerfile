FROM python:3.12-slim

# System deps for Whisper (ffmpeg) and general build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY src/ src/
COPY data/ data/

# Create runtime directories
RUN mkdir -p logs history

CMD ["python", "-m", "src.main"]
