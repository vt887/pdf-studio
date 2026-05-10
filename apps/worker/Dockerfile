FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY packages/document-model /app/packages/document-model
COPY packages/pdf-renderer /app/packages/pdf-renderer
COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir -e /app/packages/document-model -e /app/packages/pdf-renderer

WORKDIR /app/apps/worker

CMD ["python", "-m", "worker.main", "--queue", "default"]
