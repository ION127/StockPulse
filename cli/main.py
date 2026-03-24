"""
주식 이상값 AI 분석기 - CLI 스크립트

실행 방법:
  python -m cli.main             # 즉시 1회 실행
  python -m cli.main --schedule  # 스케줄러 모드 (60분마다 자동 실행)
  python -m cli.main --demo      # 데모 모드 (API 없이 구조 확인)
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from core.stock_categories import STOCK_CATEGORIES, get_all_us_tickers, get_all_kr_tickers
from core.stock_fetcher import fetch_us_stocks, fetch_kr_stocks, detect_anomalies, \
    get_sector_anomaly_summary, classify_event_type
from core.news_fetcher import fetch_news_for_anomaly, format_news_for_prompt
from core.ai_analyzer import analyze_anomaly, analyze_sector_trends

EVENT_TYPE_LABEL = {
    "INDIVIDUAL": "개별 이벤트 (해당 종목만 이상값)",
    "SECTOR":     "섹터 이벤트 (섹터 전체 움직임)",
    "MARKET":     "시장 전체 이벤트 (매크로 이슈)",
}


def print_separator(char="=", width=70):
    print(char * width)


def run_analysis(demo_mode: bool = False):
    """메인 분석 파이프라인"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_separator()
    print(f"  주식 이상값 AI 분석기")
    print(f"  실행 시각: {now}")
    print_separator()

    print("\n[1/4] 주식 데이터 수집 중...")
    threshold_pct = float(os.getenv("ANOMALY_THRESHOLD_PERCENT", "8.0"))
    threshold_z = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0"))

    if demo_mode:
        logger.info("데모 모드: 샘플 데이터 사용")
        all_anomalies = [
            {"ticker": "AVAV", "date": datetime.now().date(), "return_pct": 8.5,
             "zscore": 3.1, "close_price": 175.30, "volume": 2500000,
             "direction": "급등", "is_recent": True},
            {"ticker": "KR:047810", "date": datetime.now().date(), "return_pct": -6.2,
             "zscore": -2.8, "close_price": 52000, "volume": 1800000,
             "direction": "급락", "is_recent": True},
        ]
    else:
        us_data = fetch_us_stocks(get_all_us_tickers())
        kr_data = fetch_kr_stocks(get_all_kr_tickers())
        all_stock_data = {**us_data, **kr_data}
        print(f"    수집 완료: 미국 {len(us_data)}개, 한국 {len(kr_data)}개 종목")

        print(f"\n[2/4] 이상값 탐지 중 (기준: +-{threshold_pct}% 또는 Z-score +-{threshold_z})...")
        all_anomalies = detect_anomalies(all_stock_data,
                                         percent_threshold=threshold_pct,
                                         zscore_threshold=threshold_z)

    recent_anomalies = [a for a in all_anomalies if a.get("is_recent", False)]
    print(f"    전체 이상값: {len(all_anomalies)}건 / 최근 5일: {len(recent_anomalies)}건")

    if not recent_anomalies:
        print("\n최근 5일간 주요 이상값이 감지되지 않았습니다.")
        return

    print("\n[3/4] 섹터별 분류 중...")
    classified = classify_event_type(recent_anomalies, STOCK_CATEGORIES)
    sector_anomalies = get_sector_anomaly_summary(classified, STOCK_CATEGORIES)

    print("\n  감지된 이상값 요약:")
    for sector, anomalies in sector_anomalies.items():
        print(f"    {sector}: {len(anomalies)}개 종목")
        for a in anomalies:
            etype = EVENT_TYPE_LABEL.get(a.get("event_type", "INDIVIDUAL"), "")
            print(f"      - {a['ticker']}: {a['return_pct']:+.1f}% ({a['direction']}) | {etype}")

    print("\n[4/4] AI 분석 중 (Gemini API)...")

    if demo_mode or not os.getenv("GROQ_API_KEY"):
        if not os.getenv("GROQ_API_KEY"):
            print("\n  GROQ_API_KEY가 설정되지 않았습니다.")
        _print_summary_only(sector_anomalies)
        return

    trend_analysis = analyze_sector_trends(sector_anomalies)
    print_separator("-")
    print("[한국어 종합 분석]")
    print(trend_analysis["ko"])
    print("\n[English Macro Analysis]")
    print(trend_analysis["en"])

    analyzed_count = 0
    for sector, anomalies in sector_anomalies.items():
        for anomaly in anomalies[:2]:
            if analyzed_count >= 5:
                break
            ticker = anomaly["ticker"]
            event_type = anomaly.get("event_type", "INDIVIDUAL")
            print_separator("-")
            print(f"  {ticker} | {sector} | {EVENT_TYPE_LABEL.get(event_type, '')}")
            print_separator("-")

            cat_data = STOCK_CATEGORIES.get(sector, {})
            news_data = fetch_news_for_anomaly(
                ticker=ticker, category_name=sector,
                keywords_en=cat_data.get("keywords_en", [ticker]),
                keywords_kr=cat_data.get("keywords_kr", []),
            )
            analysis = analyze_anomaly(
                ticker=ticker, category=sector,
                return_pct=anomaly["return_pct"], direction=anomaly["direction"],
                date=str(anomaly["date"]), close_price=anomaly["close_price"],
                news_text=format_news_for_prompt(news_data),
                event_type=event_type,
                sector_peer_count=anomaly.get("sector_peer_count", 1),
                moving_sector_count=anomaly.get("moving_sector_count", 1),
            )
            print("\n[한국어 분석]")
            print(analysis["ko"])
            print("\n[English Analysis]")
            print(analysis["en"])
            analyzed_count += 1

    print_separator()
    print(f"  분석 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_separator()


def _print_summary_only(sector_anomalies: dict):
    print_separator("-")
    for sector, anomalies in sector_anomalies.items():
        print(f"\n[{sector}]")
        for a in anomalies:
            icon = "DOWN" if "급락" in a["direction"] else "UP"
            print(f"  [{icon}] {a['ticker']}: {a['return_pct']:+.2f}% "
                  f"(Z: {a['zscore']:+.2f}) | 종가: {a['close_price']}")


def start_scheduler():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("apscheduler 필요: pip install apscheduler")
        sys.exit(1)

    interval_minutes = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60"))
    scheduler = BlockingScheduler()
    scheduler.add_job(run_analysis, "interval", minutes=interval_minutes,
                      next_run_time=datetime.now())
    print(f"스케줄러 시작: {interval_minutes}분마다 실행 | Ctrl+C로 종료")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n스케줄러 종료.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="주식 이상값 AI 분석기")
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.schedule:
        start_scheduler()
    else:
        run_analysis(demo_mode=args.demo)
