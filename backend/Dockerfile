FROM python:3.12-slim

WORKDIR /app

# System packages:
#   libzbar0       – barcode scanning (pyzbar)
#   libgl1         – OpenCV headless
#   libglib2.0-0   – OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
        libzbar0 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
