FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py enrich.py server.py db.py utils.py ./
COPY targets.txt ./
COPY templates/ ./templates/
COPY static/ ./static/

# Seed database
COPY resorts.db /app/data-seed/resorts.db

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

VOLUME ["/app/data"]

ENV DB_PATH=/app/data/resorts.db
ENV OLLAMA_URL=http://host.docker.internal:11434

EXPOSE 5001

CMD ["./entrypoint.sh"]