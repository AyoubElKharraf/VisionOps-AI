FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py demo_roi.py alert_client.py onnx_engine.py export_onnx.py roi_manager.py ./
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh && mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV YOLO_MODEL=yolov8n.pt
ENV USE_ONNX=true

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "demo_roi.py", "--skip-benchmark", "--max-frames", "0", "--stream-detections", "--post-alerts", "--sync-roi", "--stream-every", "2", "--api-url", "http://backend:8001"]
