# ---- Python + Node + Chromium (for Mermaid CLI / SVG) ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUPPETEER_SKIP_DOWNLOAD=1 \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    MMDC_PATH=/usr/local/bin/mmdc

# System deps:
# - nodejs/npm for @mermaid-js/mermaid-cli
# - chromium for Puppeteer-backed SVG rendering
# - fonts for glyph coverage
# - curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
      nodejs npm chromium \
      fonts-liberation fonts-noto-color-emoji \
      ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

# Mermaid CLI
RUN npm install -g @mermaid-js/mermaid-cli

WORKDIR /app

# Minimal Python deps for the service
# NOTE: python-multipart is required by FastAPI whenever you use UploadFile/Form
RUN pip install --no-cache-dir fastapi uvicorn python-dotenv python-multipart

# Copy application code (don’t bake .env)
COPY app ./app

# Non-root user
RUN useradd -m -u 10001 appuser
USER appuser

EXPOSE 8911

# Simple healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -fsS http://localhost:8911/health || exit 1

# Start the API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8911"]
