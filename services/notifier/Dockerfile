FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Phase 3: slack-sdk, sendgrid 추가 예정
# RUN pip install slack-sdk

COPY services/notifier/ ./

CMD ["python", "main.py"]
