FROM python:3.12-slim AS source-package
WORKDIR /source
COPY . .
ARG SOURCE_REVISION=unknown
RUN python scripts/package_source.py /source /out --revision "$SOURCE_REVISION"

FROM python:3.12-slim AS runtime-dependencies
LABEL org.opencontainers.image.licenses="AGPL-3.0-only"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends poppler-utils fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scripts/package_licences.py /tmp/package_licences.py
RUN python /tmp/package_licences.py /dependency-legal && rm /tmp/package_licences.py

FROM runtime-dependencies AS dependency-sources
COPY scripts/package_dependency_sources.py /tmp/package_dependency_sources.py
RUN python /tmp/package_dependency_sources.py /dependency-legal/dependency-inventory.json /source-archives

FROM runtime-dependencies
COPY server/ ./
COPY LICENSE COPYRIGHT THIRD_PARTY_NOTICES.md ./legal/
COPY --from=source-package /out/ ./legal/
COPY --from=dependency-sources /source-archives/ ./legal/
RUN cp /dependency-legal/* /app/legal/ && rm -rf /dependency-legal
COPY LICENSE COPYRIGHT ./
RUN mkdir /data && chown 99:100 /data
USER 99:100
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/session',timeout=3)"
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--bind", "0.0.0.0:8788", "--workers", "1", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
