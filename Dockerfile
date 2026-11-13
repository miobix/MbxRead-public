# API image: FastAPI + uvicorn on :8002. Data (SQLite files) lives in the /data volume.
FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MBXREAD_DATA_DIR=/data

WORKDIR /app

# Dependencies first: a code-only change reuses this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data && chown app /data

COPY server/ server/
COPY translate_svc/ translate_svc/
COPY import_tools/ import_tools/

USER app
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/api/health', timeout=4)"]

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8002"]
