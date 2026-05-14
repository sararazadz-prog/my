FROM python:3.11-slim

RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

RUN mkdir -p /data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
