# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --home /app app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
RUN mkdir -p /app/uploads && chown -R app:app /app/uploads

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=4).status == 200 else 1)"

# Workers are stateless (sessions, rate limits and notifications live in PostgreSQL), so scaling is safe.
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3} --timeout 120 --forwarded-allow-ips='*' --access-logfile -"]
