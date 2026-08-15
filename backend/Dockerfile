# Multi-stage / optimized slim image with FFmpeg
FROM python:3.11-slim

# Prevent Python from writing .pyc files & enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY . .

# Ensure storage directories exist
RUN mkdir -p /app/data /app/temp

# Expose default port
EXPOSE 10000

# Start Uvicorn bound to the dynamic Render $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
