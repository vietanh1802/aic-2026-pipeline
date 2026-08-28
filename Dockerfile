# syntax=docker/dockerfile:1.7


FROM python:3.11-slim AS api

ARG AIC_VERSION=0.0.0-dev
ARG AIC_COMMIT=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AIC_VERSION=${AIC_VERSION} \
    AIC_COMMIT=${AIC_COMMIT}

WORKDIR /srv/aic

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.13.0+cpu \
        torchvision==0.28.0+cpu \
    && python -m pip install -r /tmp/requirements.txt

COPY backend/app ./app
COPY backend/asr_retrieval ./asr_retrieval
COPY backend/scripts ./scripts

RUN mkdir -p \
    /opt/aic/indexes \
    /opt/aic/static/images \
    /opt/aic/data \
    /opt/aic/asr \
    /opt/aic/model-cache

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.11-slim AS asr

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/aic

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-asr.txt /tmp/requirements-asr.txt

RUN python -m pip install --upgrade pip

COPY docker-wheels/torch-2.13.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl /tmp/torch-2.13.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl

RUN python -m pip install "/tmp/torch-2.13.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl" \
    && rm "/tmp/torch-2.13.0+cpu-cp311-cp311-manylinux_2_28_x86_64.whl"

RUN python -m pip install -r /tmp/requirements-asr.txt

COPY backend/asr_api ./asr_api
COPY backend/asr_retrieval ./asr_retrieval

RUN mkdir -p \
    /opt/aic/asr \
    /opt/aic/model-cache

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "asr_api.main:app", "--host", "0.0.0.0", "--port", "8001"]


FROM node:22-alpine AS drive-proxy

ENV NODE_ENV=production \
    PORT=5000

WORKDIR /srv/drive-video-proxy

COPY drive-video-proxy/package*.json ./
RUN npm ci --omit=dev

COPY drive-video-proxy/server.js ./

EXPOSE 5000

CMD ["node", "server.js"]


FROM caddy:2-builder-alpine AS caddy-builder

RUN xcaddy build --with github.com/caddy-dns/cloudflare


FROM caddy:2-alpine AS caddy

COPY --from=caddy-builder /usr/bin/caddy /usr/bin/caddy