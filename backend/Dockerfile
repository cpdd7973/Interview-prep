FROM python:3.12-slim
WORKDIR /app

# Create non-root user for security (Red Flag #5 from devops-deployment)
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install system dependencies (ffmpeg is required by Whisper)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Dependencies
COPY requirements.txt .
# Install setuptools first to fix the 'pkg_resources' error for Whisper
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy source with correct ownership
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
