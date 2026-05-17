FROM python:3.12-slim

WORKDIR /app

# OpenCV runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 80

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "1", "--timeout", "60", "app:app"]
