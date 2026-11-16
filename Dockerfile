# MbxRead image: FastAPI + uvicorn on :8002, serving the API and the static web build.
# Data (SQLite files) lives in the /data volume.
FROM node:24.18.0-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM denoland/deno:bin-2.9.6@sha256:4cf0029b9aeeeed5efcbb71828737f0d7c8c8a20072df960e51a5679ef0d21ba AS deno

FROM python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

LABEL org.opencontainers.image.source=https://github.com/miobix/MbxRead-public

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

# yt-dlp needs a JS runtime for YouTube; it finds deno on PATH.
COPY --from=deno /deno /usr/local/bin/deno

COPY server/ server/
COPY translate_svc/ translate_svc/
COPY import_tools/ import_tools/
COPY --from=web /web/out web/out/

USER app
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/api/health', timeout=4)"]

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8002"]
