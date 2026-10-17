FROM python:3.12-slim
WORKDIR /relay
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home relay && mkdir /data && chown relay /data
COPY relay.py .
USER relay
EXPOSE 8790
CMD ["gunicorn", "--bind", "0.0.0.0:8790", "--workers", "1", "--threads", "4", "--access-logfile", "/dev/null", "relay:app"]
