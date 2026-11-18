FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Toronto \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000 \
    DATABASE_PATH=/data/gas.db

WORKDIR /app

RUN groupadd --gid 10001 gastracker \
    && useradd --uid 10001 --gid gastracker --no-create-home gastracker \
    && mkdir /data \
    && chown gastracker:gastracker /data

COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install .

COPY config.toml alembic.ini ./
COPY migrations ./migrations

USER gastracker
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('WEB_PORT', '8000') + '/health', timeout=2)"

CMD ["python", "-m", "gastracker"]