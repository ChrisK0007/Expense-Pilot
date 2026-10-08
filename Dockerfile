FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py reset_password.py billing.py billing_core.py tax_core.py receipt_core.py tracking.py security.py date_core.py location_core.py expense_core.py features.py gunicorn.conf.py ./
COPY static ./static
COPY datasets ./datasets
RUN mkdir /data && chown 99:100 /data
USER 99:100
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/session',timeout=3)"
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--bind", "0.0.0.0:8788", "--workers", "1", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
