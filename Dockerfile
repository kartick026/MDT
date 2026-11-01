# Root Dockerfile: same-origin React UI and deterministic hosted API for Render, Railway, Fly.io, etc.
FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_URL=/ VITE_ENABLE_LOCAL_DASHBOARD=false
RUN npm run build

FROM python:3.11-alpine3.24 AS dependencies
WORKDIR /build
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=5
RUN apk add --no-cache build-base
COPY backend/requirements-hosted.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip wheel --wheel-dir=/wheels -r requirements-hosted.txt

FROM python:3.11-alpine3.24 AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000 STATIC_FRONTEND_DIR=/app/web
RUN apk upgrade --no-cache && apk add --no-cache git ca-certificates libstdc++
COPY backend/requirements-hosted.txt ./
RUN --mount=type=bind,from=dependencies,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-hosted.txt \
    && pip uninstall -y pip setuptools wheel
RUN addgroup -g 10001 mdt && adduser -D -u 10001 -G mdt mdt
COPY --chown=mdt:mdt backend/ ./
COPY --from=frontend --chown=mdt:mdt /web/dist/ ./web/
USER mdt
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-server-header"]
