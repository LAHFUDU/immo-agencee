# syntax=docker/dockerfile:1
# Single-container image for Render (or any PaaS): the API serves the React build itself
# (FRONTEND_DIST), so there is one URL and cookies stay same-origin. The database is external
# (Neon) and comes from DATABASE_URL. Docker Compose on a VPS still uses backend/ and frontend/.

# 1) Build the React app
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# 2) API + static files
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/app/static UPLOAD_DIR=/app/uploads TRUST_PROXY_HEADERS=true
WORKDIR /app

RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --home /app app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/alembic.ini .
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=frontend /src/dist ./static
RUN mkdir -p /app/uploads && chown -R app:app /app/uploads

USER app
EXPOSE 8000

# On start: migrations + reference data, reminders loop in the background, then the web server.
# Render injects PORT and RENDER_EXTERNAL_URL (used for invitation / reset links).
CMD ["sh", "-c", "export FRONTEND_URL=\"${FRONTEND_URL:-$RENDER_EXTERNAL_URL}\" && export CORS_ORIGINS=\"${CORS_ORIGINS:-$FRONTEND_URL}\" && alembic upgrade head && python -m app.cli init && (python -m app.cli scheduler &) && exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 120 --forwarded-allow-ips='*' --access-logfile -"]
