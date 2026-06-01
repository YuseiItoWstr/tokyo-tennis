FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY notify/ ./notify/

RUN chmod +x /app/notify/docker_entrypoint.sh /app/notify/run_all.sh

ENV PYTHON=python3
ENV DATA_DIR=/app/data
ENV PYTHONDONTWRITEBYTECODE=1
