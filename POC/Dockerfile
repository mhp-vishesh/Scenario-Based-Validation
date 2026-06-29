# Scenario-Based Validation POC
# Multi-stage build for GPU-accelerated Cosmos inference

# Base stage with CUDA support
FROM nvidia/cuda:12.1-devel-ubuntu22.04 AS base

# Prevent interactive prompts during install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3.10-venv \
    git \
    wget \
    curl \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Set Python alias
RUN ln -sf /usr/bin/python3.10 /usr/bin/python

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install Cosmos dependencies
RUN pip install --no-cache-dir \
    transformers \
    accelerate \
    safetensors \
    diffusers \
    einops \
    omegaconf

# -----------------------------------------------------------
# Development stage (includes dev tools)
FROM base AS dev

RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    black \
    ruff \
    mypy

COPY . .

# Run tests
RUN python -m pytest tests/ -v --tb=short || true

# Default: run dashboard
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]

# -----------------------------------------------------------
# Production stage (minimal)
FROM base AS prod

# Copy application code
COPY src/ ./src/
COPY dashboard/ ./dashboard/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Create directories for outputs and models
RUN mkdir -p outputs seeds /opt/cosmos/models

# Environment variables
ENV COSMOS_PREDICT_CHECKPOINT=/opt/cosmos/models/predict-2.5-14b
ENV COSMOS_TRANSFER_CHECKPOINT=/opt/cosmos/models/transfer-2.5-7b
ENV COSMOS_REASON_CHECKPOINT=/opt/cosmos/models/reason-2

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default command: run dashboard
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]

# -----------------------------------------------------------
# Generation stage (for batch processing)
FROM base AS generator

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

RUN mkdir -p outputs seeds /opt/cosmos/models

ENV COSMOS_PREDICT_CHECKPOINT=/opt/cosmos/models/predict-2.5-14b
ENV COSMOS_TRANSFER_CHECKPOINT=/opt/cosmos/models/transfer-2.5-7b

ENTRYPOINT ["python", "scripts/generate.py"]

# -----------------------------------------------------------
# Validator stage (for running judge)
FROM base AS validator

COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/

RUN mkdir -p outputs /opt/cosmos/models

ENV COSMOS_REASON_CHECKPOINT=/opt/cosmos/models/reason-2

ENTRYPOINT ["python", "scripts/validate.py"]
