"""
Stock Collector 서비스 — Phase 3

역할:
  - yfinance (미국) / pykrx (한국) 로 주가 데이터 수집
  - Kafka Topic 'stock.raw.us', 'stock.raw.kr'에 배치로 발행
  - K8s CronJob으로 평일 30분마다 실행 (1회 실행 후 종료)

메시지 형식 (stock.raw.us / stock.raw.kr):
  key   : "batch"
  value : {
      "market"    : "us" | "kr",
      "timestamp" : ISO8601,
      "stocks"    : {
          "<ticker>": {
              "<YYYY-MM-DD HH:MM:SS>": {
                  "Open": float, "High": float, "Low": float,
                  "Close": float, "Volume": int
              }, ...
          }, ...
      }
  }
"""

import json
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("stock-collector")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
PERIOD_DAYS = int(os.getenv("STOCK_PERIOD_DAYS", "30"))


def _build_producer():
    from confluent_kafka import Producer

    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "message.max.bytes": 10_485_760,   # 10 MB
        "queue.buffering.max.messages": 100,
    })


def _delivery_report(err, msg):
    if err:
        logger.error(f"전송 실패 [{msg.topic()}]: {err}")
    else:
        logger.debug(f"발행 완료 [{msg.topic()} p{msg.partition()}] {len(msg.value())} bytes")


def _df_to_dict(df) -> dict:
    """DataFrame → JSON 직렬화 가능한 dict (날짜 key)"""
    df_copy = df.copy()
    df_copy.index = df_copy.index.astype(str)
    return df_copy.to_dict(orient="index")


def publish_batch(producer, topic: str, market: str, stock_data: dict) -> int:
    """stock_data({ticker: DataFrame})를 하나의 Kafka 메시지로 발행."""
    serialized = {ticker: _df_to_dict(df) for ticker, df in stock_data.items()}
    payload = {
        "market": market,
        "timestamp": datetime.now().isoformat(),
        "stocks": serialized,
    }
    value = json.dumps(payload, default=str).encode("utf-8")
    producer.produce(topic, key="batch", value=value, callback=_delivery_report)
    producer.flush()
    logger.info(f"[{topic}] {len(serialized)}개 종목 발행 완료 ({len(value)/1024:.1f} KB)")
    return len(serialized)


def main():
    logger.info(f"[stock-collector] 시작 | Kafka: {KAFKA_BOOTSTRAP}")

    try:
        from core.stock_categories import get_all_us_tickers, get_all_kr_tickers
        from core.stock_fetcher import fetch_us_stocks, fetch_kr_stocks
    except ImportError as e:
        logger.error(f"core 모듈 임포트 실패: {e}")
        sys.exit(1)

    producer = _build_producer()

    # ── 미국 주식 수집 ──
    us_tickers = get_all_us_tickers()
    logger.info(f"미국 주식 {len(us_tickers)}개 수집 시작")
    us_data = fetch_us_stocks(us_tickers, period_days=PERIOD_DAYS)
    if us_data:
        publish_batch(producer, "stock.raw.us", "us", us_data)
    else:
        logger.warning("미국 주식 수집 결과 없음 — stock.raw.us 발행 생략")

    # ── 한국 주식 수집 ──
    kr_tickers = get_all_kr_tickers()
    logger.info(f"한국 주식 {len(kr_tickers)}개 수집 시작")
    kr_data = fetch_kr_stocks(kr_tickers, period_days=PERIOD_DAYS)
    if kr_data:
        publish_batch(producer, "stock.raw.kr", "kr", kr_data)
    else:
        logger.warning("한국 주식 수집 결과 없음 — stock.raw.kr 발행 생략")

    logger.info("[stock-collector] 완료 — 프로세스 종료")


if __name__ == "__main__":
    main()
