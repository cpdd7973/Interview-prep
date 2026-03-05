FROM python:3.12-slim
WORKDIR /app

# Create non-root user for security (Red Flag #5 from devops-deployment)
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source with correct ownership
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
