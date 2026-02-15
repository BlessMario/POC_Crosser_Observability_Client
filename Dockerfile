FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir -U pip

# minimal OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

COPY app /app/app
COPY certs /app/certs

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8000"]
