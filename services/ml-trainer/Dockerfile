FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (LightGBM 빌드에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY core/ ./core/
COPY services/ml-trainer/main.py ./main.py

# 모델 저장 디렉토리
RUN mkdir -p /app/models

ENV MODEL_DIR=/app/models
ENV PYTHONPATH=/app

CMD ["python", "main.py"]
