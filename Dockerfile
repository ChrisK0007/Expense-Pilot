FROM python:3.12-slim AS source-package
WORKDIR /source
COPY . .
ARG SOURCE_REVISION=unknown
RUN python scripts/package_source.py /source /out --revision "$SOURCE_REVISION"

FROM python:3.12-slim AS sqlite-build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY scripts/build_sqlite.py /build_sqlite.py
RUN python /build_sqlite.py --output /opt/sqlite

FROM python:3.12-slim AS runtime-dependencies
LABEL org.opencontainers.image.licenses="AGPL-3.0-only"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
COPY --from=sqlite-build /opt/sqlite/ /opt/sqlite/
ENV LD_LIBRARY_PATH=/opt/sqlite/lib
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends poppler-utils fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY server/healthcheck.py /tmp/healthcheck.py
RUN python -c "import sys; sys.path.insert(0, '/tmp'); from healthcheck import check_runtime; print('Python SQLite:', check_runtime())" && rm /tmp/healthcheck.py
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
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s CMD ["python", "healthcheck.py"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--bind", "0.0.0.0:8788", "--workers", "1", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
