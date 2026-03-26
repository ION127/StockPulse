"""
DART (금융감독원) 재무제표 데이터 수집
- OpenDartReader 라이브러리 (무료 API 키 필요)
- PER, PBR, ROE, 부채비율, 영업이익률, EPS
- https://opendart.fss.or.kr 에서 API 키 발급 (무료)
"""

import logging
import os
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DART_API_KEY = os.getenv("DART_API_KEY", "")


def _get_dart():
    """OpenDartReader 클라이언트 (lazy init)"""
    if not DART_API_KEY:
        return None
    try:
        import OpenDartReader
        return OpenDartReader(DART_API_KEY)
    except ImportError:
        logger.debug("[DART] OpenDartReader 미설치")
        return None
    except Exception as e:
        logger.warning(f"[DART] 클라이언트 초기화 실패: {e}")
        return None


def get_financial_ratios(ticker: str) -> dict:
    """
    최근 사업보고서 기준 주요 재무비율

    Returns:
        dict keys: debt_ratio, roe, operating_margin, net_margin,
                   current_ratio, eps, bps
    """
    dart = _get_dart()
    if not dart:
        return {}

    try:

        clean = ticker.replace("KR:", "").replace(".KS", "").replace(".KQ", "")
        corp_code = dart.find_corp_code(clean)
        if not corp_code:
            return {}

        year = pd.Timestamp.now().year - 1  # 전년도 사업보고서
        fs = dart.finstate_all(corp_code, year, reprt_code="11011")

        if fs is None or fs.empty:
            return {}

        result = {}
        for _, row in fs.iterrows():
            account = str(row.get("account_nm", ""))
            raw_val = str(row.get("thstrm_amount", "")).replace(",", "").strip()
            try:
                val = float(raw_val) if raw_val and raw_val not in ("-", "") else None
            except ValueError:
                val = None

            if val is None:
                continue

            if "부채비율" in account:
                result["debt_ratio"] = val
            elif "자기자본이익률" in account or "ROE" in account:
                result["roe"] = val
            elif "영업이익률" in account:
                result["operating_margin"] = val
            elif "순이익률" in account or "당기순이익률" in account:
                result["net_margin"] = val
            elif "유동비율" in account:
                result["current_ratio"] = val
            elif "주당순이익" in account or "EPS" in account:
                result["eps"] = val
            elif "주당순자산" in account or "BPS" in account:
                result["bps"] = val

        return result

    except Exception as e:
        logger.warning(f"[DART] 재무비율 수집 실패 ({ticker}): {e}")
        return {}


def get_earnings_surprise(ticker: str) -> Optional[float]:
    """
    최근 분기 어닝 서프라이즈 (%)
    yfinance 기반 (DART 없이도 동작)

    Returns: (실제EPS - 예측EPS) / |예측EPS| * 100
    """
    try:
        import yfinance as yf

        clean = ticker.replace("KR:", "")
        # 한국 주식은 .KS (KRX), .KQ (KOSDAQ)
        for suffix in [".KS", ".KQ"]:
            try:
                stock = yf.Ticker(clean + suffix)
                hist = stock.earnings_history
                if hist is not None and not hist.empty:
                    latest = hist.iloc[-1]
                    actual = latest.get("epsActual")
                    estimate = latest.get("epsEstimate")
                    if actual is not None and estimate and abs(estimate) > 1e-6:
                        return round((float(actual) - float(estimate)) / abs(float(estimate)) * 100, 2)
            except Exception:
                continue
        return None

    except Exception as e:
        logger.debug(f"[DART] 어닝 서프라이즈 수집 실패 ({ticker}): {e}")
        return None


def get_analyst_consensus(ticker: str) -> dict:
    """
    애널리스트 컨센서스 (yfinance)

    Returns: recommendation, target_price, upside_pct
    """
    try:
        import yfinance as yf

        clean = ticker.replace("KR:", "")
        for suffix in [".KS", ".KQ"]:
            try:
                stock = yf.Ticker(clean + suffix)
                info = stock.info
                if not info:
                    continue

                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                target_price = info.get("targetMeanPrice")
                recommendation = info.get("recommendationKey", "")

                result = {"recommendation": recommendation}
                if target_price and current_price and current_price > 0:
                    result["target_price"] = target_price
                    result["analyst_upside_pct"] = round(
                        (target_price / current_price - 1) * 100, 2
                    )
                    result["analyst_count"] = info.get("numberOfAnalystOpinions", 0)
                return result
            except Exception:
                continue
        return {}

    except Exception as e:
        logger.debug(f"[DART] 애널리스트 컨센서스 수집 실패 ({ticker}): {e}")
        return {}


# ── Look-ahead Bias 방지: 공시 이벤트 (날짜 기반) ─────────────────────────

# 공시 종류 → 수치 매핑 (음수=부정, 양수=긍정)
_DISCLOSURE_SENTIMENT = {
    "유상증자":        -2,   # 주식 희석
    "무상증자":        +2,   # 주주 환원 신호
    "자기주식취득":    +2,   # 자사주 매입 = 주가 부양
    "자기주식소각":    +3,   # 강력한 주주 환원
    "전환사채":        -1,   # 잠재적 희석
    "신주인수권부사채": -1,
    "대규모내부거래":  -1,
    "주요사항보고":     0,   # 중립 (세부 확인 필요)
    "수시공시":         0,
    "실적공시":         0,   # 실적은 서프라이즈로 별도 처리
}

# 분기말 → 실제 공시 가능 최소 날짜 (look-ahead lag)
# 1분기(3월말) → 5월15일, 2분기(6월말) → 8월15일, 3분기(9월말) → 11월15일, 연간(12월말) → 3월31일
_QUARTER_ANNOUNCE_OFFSET = {1: 45, 2: 45, 3: 45, 4: 90}  # days after quarter end


def get_disclosure_events(ticker: str, days_back: int = 90) -> pd.DataFrame:
    """
    DART 공시 이벤트를 날짜 인덱스 DataFrame으로 반환 (Look-ahead bias 방지)

    공시 발표일 기준으로 피처를 생성하므로 미래 정보 누수 없음

    Returns columns: date, disclosure_sentiment, has_capital_increase,
                     has_buyback, has_bond, disclosure_count
    """
    dart = _get_dart()
    if not dart:
        return pd.DataFrame()

    try:
        from datetime import datetime, timedelta

        clean = ticker.replace("KR:", "").replace(".KS", "").replace(".KQ", "")
        corp_code = dart.find_corp_code(clean)
        if not corp_code:
            return pd.DataFrame()

        end_date   = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        disclosures = dart.list(
            corp_code,
            start=start_date.strftime("%Y%m%d"),
            end=end_date.strftime("%Y%m%d"),
            kind_detail="",
        )

        if disclosures is None or disclosures.empty:
            return pd.DataFrame()

        # 날짜별 집계
        records = []
        for _, row in disclosures.iterrows():
            rcept_dt = str(row.get("rcept_dt", ""))
            if len(rcept_dt) != 8:
                continue

            report_nm = str(row.get("report_nm", ""))
            sentiment = 0
            for keyword, score in _DISCLOSURE_SENTIMENT.items():
                if keyword in report_nm:
                    sentiment = score
                    break

            records.append({
                "date":               pd.to_datetime(rcept_dt),
                "disclosure_sentiment": sentiment,
                "has_capital_increase": int("유상증자" in report_nm),
                "has_buyback":          int("자기주식취득" in report_nm or "자기주식소각" in report_nm),
                "has_bond":             int("사채" in report_nm),
            })

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records).set_index("date")
        # 날짜별 집계 (같은 날 여러 공시 가능)
        agg = df.resample("D").agg({
            "disclosure_sentiment": "sum",
            "has_capital_increase": "max",
            "has_buyback":          "max",
            "has_bond":             "max",
        })
        agg["disclosure_count"] = df.resample("D").size()

        # 최근 7일/30일 rolling sum (이벤트 누적 효과)
        agg["disclosure_sentiment_7d"]  = agg["disclosure_sentiment"].rolling(7, min_periods=1).sum()
        agg["disclosure_sentiment_30d"] = agg["disclosure_sentiment"].rolling(30, min_periods=1).sum()

        return agg

    except Exception as e:
        logger.warning(f"[DART] 공시 이벤트 수집 실패 ({ticker}): {e}")
        return pd.DataFrame()


def get_financial_ratios_with_lag(ticker: str) -> dict:
    """
    재무비율 + 공시 가능 최소 날짜 반환 (Look-ahead bias 방지용)

    Returns:
        dict with keys: data (재무비율), available_from (이 날짜 이후에만 사용 가능)
    """
    from datetime import datetime, timedelta

    ratios = get_financial_ratios(ticker)
    if not ratios:
        return {"data": {}, "available_from": None}

    # 보수적으로 현재 분기 종료 후 60일
    now = datetime.now()
    quarter_end_month = ((now.month - 1) // 3) * 3 + 3
    quarter_end = datetime(now.year, quarter_end_month, 30)
    available_from = quarter_end + timedelta(days=60)

    return {
        "data":           ratios,
        "available_from": available_from,
    }
