# Dockerfile for SoC Validation Infrastructure

# Base stage with common dependencies
FROM python:3.12-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    gcc \
    g++ \
    make \
    telnet \
    openssh-client \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY src/ /app/src/
COPY config/ /app/config/

# Create necessary directories
RUN mkdir -p /app/logs /data/artifacts /data/tests

# =============================================================================
# Device Manager Stage
# =============================================================================
FROM base AS device-manager

# Set environment for device manager
ENV SERVICE_NAME=device-manager
ENV PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run device manager API
CMD ["uvicorn", "src.device_manager.api:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Notification Service Stage
# =============================================================================
FROM base AS notification

# Set environment for notification service
ENV SERVICE_NAME=notification
ENV PORT=9000

# Expose port
EXPOSE 9000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

# Run notification service
CMD ["uvicorn", "src.notifications.api:app", "--host", "0.0.0.0", "--port", "9000"]