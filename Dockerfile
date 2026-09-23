# Mindbaton in a container. Your data lives in the /data volume; nothing else needs to persist.
#   docker build -t mindbaton . && docker run -d -p 3004:3004 -v mindbaton-data:/data --name mindbaton mindbaton
FROM python:3.13-slim

# brain.py tells real words from names with the system word list; no pip packages are needed.
RUN apt-get update && apt-get install -y --no-install-recommends wamerican && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --home-dir /data mindbaton && mkdir -m 700 /data && chown mindbaton /data

WORKDIR /app
COPY . .

ENV MINDBATON_DATA=/data MINDBATON_HOST=0.0.0.0 MINDBATON_PORT=3004 MINDBATON_WATCH_CLAUDE=0 PYTHONUNBUFFERED=1
USER mindbaton
VOLUME /data
EXPOSE 3004
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python3 -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['MINDBATON_PORT'], timeout=4)"
CMD ["python3", "server.py"]
