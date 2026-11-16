# Backend image for the API and the worker. Build context: ../backend
#   docker build -f infra/Dockerfile -t zentrix-backend:$(git rev-parse --short HEAD) backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARTIFACTS_DIR=/data/artifacts \
    DATA_CACHE_DIR=/data/cache \
    PREDICTIONS_DB=/data/cache/demo_trading_log.sqlite3 \
    WEB_CONCURRENCY=2 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

# libgomp1: OpenMP runtime required by the xgboost wheel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
# Editable install so path-based settings resolve to /app. The heavy [knowledge] extra (torch) is
# deliberately left out of the API image for now.
RUN pip install -e ".[llm]" \
 && useradd --create-home --uid 10001 zentrix \
 && mkdir -p /data && chown -R zentrix /data
USER zentrix

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status != 200)"
# Several worker processes (CPU-heavy tools never stall the others); metrics of all of them are aggregated through
# PROMETHEUS_MULTIPROC_DIR. --proxy-headers: the API is reachable only through the reverse proxy (see compose).
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"$WEB_CONCURRENCY\" --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
