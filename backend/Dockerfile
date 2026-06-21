# ================================================================
# Just Ask Backend — Multi-Stage Production Dockerfile
# ================================================================
# Stage 1: Build dependencies in isolated layer
# Stage 2: Slim runtime with only necessary files
# ================================================================

# -- Stage 1: Builder ------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Pre-install CPU-only PyTorch to save ~5GB of disk space (avoids downloading NVIDIA CUDA drivers)
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Copy requirements first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -- Stage 2: Runtime ------------------------------------------------
FROM python:3.11-slim AS runtime

# Security: run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY app/ ./app/
COPY .env.example ./.env.example

# Create data directories
RUN mkdir -p data models logs data/uploads data/chroma_db \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV=production \
    LOG_FORMAT=json

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
