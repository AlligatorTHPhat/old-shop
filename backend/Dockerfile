# syntax=docker/dockerfile:1
# Build context: repository root (the image also needs database/ for the first-run bootstrap).

FROM python:3.13-slim AS builder
WORKDIR /build
COPY backend/requirements.lock .
# Wheels only (no setup.py execution) and every package pinned by hash, transitive ones included.
RUN pip install --no-cache-dir --only-binary :all: --require-hashes --prefix=/install -r requirements.lock


FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEDIA_DIR=/data/media \
    FRAUD_MODEL_DIR=/data/ml \
    DATABASE_SRC=/opt/database \
    LOG_FORMAT=json \
    ENVIRONMENT=production \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

# psql is used once to load database/init.sql; curl for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /data/media /data/ml \
    && chown -R app:app /data

COPY --from=builder /install /usr/local
WORKDIR /app
# Code stays root-owned and read-only for the runtime user; only /data is writable.
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/etl ./etl
COPY --chmod=755 backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY database /opt/database

USER app
EXPOSE 8000
VOLUME ["/data/media"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
