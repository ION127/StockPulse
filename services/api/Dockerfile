FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 공유 코어 모듈 (stock_fetcher, news_fetcher, ai_analyzer, stock_categories)
COPY core/ ./core/

# API 서비스 코드 (main.py, db/, routers/, schemas/, services/)
COPY services/api/ ./

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
