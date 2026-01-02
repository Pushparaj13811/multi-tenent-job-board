FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg2 and Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/base.txt requirements/development.txt ./
RUN pip install --no-cache-dir -r development.txt

COPY . .
