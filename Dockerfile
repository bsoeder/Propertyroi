# PropertyROI web GUI. The core is standard-library only; pdfplumber is added so
# the MVBA provider can parse PDF tax-sale bid sheets.
FROM python:3.12-slim

# Don't buffer stdout (so logs show immediately) or write .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    PROPERTYROI_PROVIDER=json

WORKDIR /app

# Optional dependency: PDF parsing for MVBA bid sheets. Wheels only (no build
# toolchain needed on amd64/arm64).
RUN pip install --no-cache-dir "pdfplumber>=0.11"

# Copy only what the app needs at runtime.
COPY propertyroi/ ./propertyroi/
COPY data/ ./data/
COPY pyproject.toml README.md ./

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Simple healthcheck against the app's own endpoint (stdlib only).
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health').read()" || exit 1

CMD ["python", "-m", "propertyroi", "serve"]
