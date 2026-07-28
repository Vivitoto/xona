# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ARG APT_MIRROR=
ARG APT_SECURITY_MIRROR=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CONFIG_DIR=/config \
    XONA_STATIC_DIR=/app/static

WORKDIR /app

RUN set -eux; \
    if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|http://deb.debian.org/debian|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -n "$APT_SECURITY_MIRROR" ]; then \
        sed -i "s|http://deb.debian.org/debian-security|$APT_SECURITY_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update; \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 install -y --no-install-recommends ca-certificates ffmpeg fonts-noto-cjk util-linux; \
    rm -rf /var/lib/apt/lists/*

COPY constraints.txt ./
RUN python -m pip install --no-cache-dir -r constraints.txt
COPY backend ./backend

COPY --from=frontend-build /build/frontend/dist /app/static
COPY docker/entrypoint.sh /usr/local/bin/xona-entrypoint
COPY docker/healthcheck.py /usr/local/bin/xona-healthcheck.py

RUN chmod +x /usr/local/bin/xona-entrypoint /usr/local/bin/xona-healthcheck.py \
    && mkdir -p /config /media

EXPOSE 8732

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "/usr/local/bin/xona-healthcheck.py"]

ENTRYPOINT ["/usr/local/bin/xona-entrypoint"]
CMD ["uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8732", "--no-access-log"]
