# trackie Dockerfile - Multi-stage build

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.15-slim AS builder

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package files
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies and package (proper install, not editable)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.15-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd --create-home --shell /bin/bash trackie && \
    mkdir -p /config && \
    chown -R trackie:trackie /config

# Set working directory
WORKDIR /app

# Switch to non-root user
USER trackie

# Default configuration directory (cookies and API keys are mounted here,
# never baked into the image)
ENV CONFIG_DIR=/config

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health').raise_for_status()" || exit 1

# Expose server port
EXPOSE 8080

# Volume for configuration and the ID-to-hash mapping store
VOLUME ["/config"]

# One worker: the poller will live in-process and must not run twice
ENTRYPOINT ["gunicorn"]
CMD ["--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "trackie.app:create_app()"]
