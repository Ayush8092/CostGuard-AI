# CostGuard AI - Backend Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps needed for psycopg2 (Postgres driver) and scientific Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the sentence-transformers embedding model at BUILD time,
# not at container start time, so the running container never needs
# outbound internet access to use the FAISS knowledge layer (Part 5).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

RUN mkdir -p /app/data/uploads /app/data/faiss_index

EXPOSE 8000

# Run Alembic migrations then start the app. Using a shell form so both
# commands execute in sequence on container start.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
