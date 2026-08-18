# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

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
RUN mkdir -p /opt/aic/indexes /opt/aic/static/images

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


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
