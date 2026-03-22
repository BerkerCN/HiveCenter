FROM python:3.11-slim

# OS Dependencies for Playwright & TTS (Ghost Observer & Voice)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    ffmpeg \
    espeak \
    mpg123 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirement files first
COPY requirements.txt .

# Install dependencies (Playwright and dependencies)
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

# Copy the rest of the engine
COPY . .

# Expose ports
EXPOSE 7021
EXPOSE 7022

# Bind on all interfaces so the service is reachable when not using host network mode
CMD ["python", "bin/hive_server.py", "--host", "0.0.0.0", "--port", "7021"]
