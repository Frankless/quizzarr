FROM python:3.12-slim

ARG VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_DIR=/config \
    TZ=Europe/Brussels \
    PUID=1000 \
    PGID=1000 \
    APP_VERSION=${VERSION}

LABEL org.opencontainers.image.title="Quizzarr" \
      org.opencontainers.image.description="Un quiz à deux choix pour savoir quoi regarder ce soir dans Jellyfin" \
      org.opencontainers.image.source="https://github.com/Frankless/quizzarr" \
      org.opencontainers.image.version="${VERSION}"

WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh

VOLUME /config
EXPOSE 7980
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7980/health')" || exit 1
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7980", "--no-server-header"]
