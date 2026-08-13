FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Worker imports shared API package code
COPY apps/api /app/api_pkg
COPY apps/worker /app

ENV PYTHONPATH=/app:/app/api_pkg

CMD ["python", "-m", "worker.main"]
