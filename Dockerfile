# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CONFIG_DIR=/config \
    STORAGE_ROOTS=/a \
    XONA_STATIC_DIR=/app/static

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY constraints.txt ./
RUN python -m pip install --no-cache-dir -r constraints.txt
COPY backend ./backend

COPY --from=frontend-build /build/frontend/dist /app/static
COPY docker/entrypoint.sh /usr/local/bin/xona-entrypoint
COPY docker/healthcheck.py /usr/local/bin/xona-healthcheck.py

RUN chmod +x /usr/local/bin/xona-entrypoint /usr/local/bin/xona-healthcheck.py \
    && mkdir -p /config /a

EXPOSE 8732

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "/usr/local/bin/xona-healthcheck.py"]

ENTRYPOINT ["/usr/local/bin/xona-entrypoint"]
CMD ["uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8732"]
