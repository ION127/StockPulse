"""
LLM 기반 구조화 피처 추출
Groq(llama-3.3-70b)를 이용해 뉴스/공시 텍스트를 숫자 피처로 변환

기존 ai_analyzer.py가 텍스트 리포트를 생성하는 것과 달리,
여기서는 ML 모델 입력에 사용할 수치형 피처를 생성함.
"""

import json
import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Groq 레이트 리밋 방지 (ai_analyzer.py와 공유 클라이언트 사용)
_MIN_INTERVAL = 3.0
_last_call_ts = 0.0


def _call_groq_json(prompt: str, max_tokens: int = 200) -> Optional[dict]:
    """
    Groq 호출 → JSON 파싱
    실패 시 None 반환 (ML 파이프라인은 None 피처를 0으로 대체)
    """
    global _last_call_ts

    try:
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return None

        # 레이트 리밋 방지
        elapsed = time.time() - _last_call_ts
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial analyst. Always respond with valid JSON only. No explanation.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.1,  # 낮은 온도 = 일관된 JSON 출력
        )
        _last_call_ts = time.time()

        raw = response.choices[0].message.content.strip()

        # JSON 블록 추출
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(raw)

    except Exception as e:
        logger.debug(f"[LLM] JSON 추출 실패: {e}")
        return None


def get_news_sentiment_features(
    ticker: str,
    news_text: str,
    sector: str = "",
) -> dict:
    """
    뉴스 텍스트 → 구조화된 수치 피처

    Returns:
        dict with keys:
            llm_sentiment    : -5 ~ +5 (부정~긍정)
            llm_volatility   : 0 ~ 10 (예상 변동성)
            llm_catalyst     : 0~4 (없음/실적/M&A/매크로/섹터)
            llm_time_horizon : 0~3 (당일/단기/중기/장기 영향)
            llm_confidence   : 0 ~ 10 (분석 신뢰도)
    """
    if not news_text or len(news_text.strip()) < 20:
        return {}

    prompt = f"""Analyze this Korean stock news for ticker {ticker} ({sector} sector).
Respond with JSON only:
{{
  "sentiment": <int -5 to 5>,
  "volatility_risk": <int 0 to 10>,
  "catalyst_type": <int 0=none 1=earnings 2=ma 3=macro 4=sector>,
  "time_horizon": <int 0=intraday 1=short 2=medium 3=long>,
  "confidence": <int 0 to 10>
}}

News: {news_text[:600]}"""

    result = _call_groq_json(prompt, max_tokens=100)
    if not result:
        return {}

    return {
        "llm_sentiment":    _safe_int(result.get("sentiment"),       -5, 5),
        "llm_volatility":   _safe_int(result.get("volatility_risk"),  0, 10),
        "llm_catalyst":     _safe_int(result.get("catalyst_type"),    0, 4),
        "llm_time_horizon": _safe_int(result.get("time_horizon"),     0, 3),
        "llm_confidence":   _safe_int(result.get("confidence"),       0, 10),
    }


def get_disclosure_sentiment_features(
    ticker: str,
    disclosure_titles: list[str],
) -> dict:
    """
    공시 제목 목록 → 구조화된 수치 피처

    Returns:
        dict with keys:
            llm_disclosure_impact  : -5 ~ +5
            llm_dilution_risk      : 0 ~ 10 (주식 희석 위험)
            llm_growth_signal      : 0 ~ 10 (성장 시그널)
    """
    if not disclosure_titles:
        return {}

    titles_text = "\n".join(f"- {t}" for t in disclosure_titles[:10])

    prompt = f"""Analyze these Korean stock disclosures for {ticker}.
Respond with JSON only:
{{
  "impact": <int -5 to 5>,
  "dilution_risk": <int 0 to 10>,
  "growth_signal": <int 0 to 10>
}}

Disclosures:
{titles_text}"""

    result = _call_groq_json(prompt, max_tokens=80)
    if not result:
        return {}

    return {
        "llm_disclosure_impact": _safe_int(result.get("impact"),        -5, 5),
        "llm_dilution_risk":     _safe_int(result.get("dilution_risk"),  0, 10),
        "llm_growth_signal":     _safe_int(result.get("growth_signal"),  0, 10),
    }


def get_macro_interpretation_features(
    vix: Optional[float],
    yield_curve: Optional[float],
    usd_krw: Optional[float],
    oil_price: Optional[float],
    sector: str = "",
) -> dict:
    """
    매크로 지표 → 해당 섹터에 미치는 영향 해석

    동일한 VIX 수치도 반도체 섹터와 금융 섹터에 미치는 영향이 다름.
    LLM이 섹터별 맥락을 고려해 해석.

    Returns:
        dict with keys:
            llm_macro_sector_impact : -5 ~ +5
            llm_risk_level          : 0 ~ 10
    """
    if vix is None:
        return {}

    prompt = f"""Given these macro conditions, assess impact on {sector} sector stocks.
Respond with JSON only:
{{
  "sector_impact": <int -5 to 5>,
  "risk_level": <int 0 to 10>
}}

Macro data:
- VIX: {vix:.1f}
- Yield Curve (10Y-3M): {yield_curve:.2f if yield_curve else 'N/A'}%
- USD/KRW: {usd_krw:.0f if usd_krw else 'N/A'}
- Oil (WTI): {oil_price:.1f if oil_price else 'N/A'}
- Sector: {sector}"""

    result = _call_groq_json(prompt, max_tokens=80)
    if not result:
        return {}

    return {
        "llm_macro_sector_impact": _safe_int(result.get("sector_impact"), -5, 5),
        "llm_risk_level":          _safe_int(result.get("risk_level"),     0, 10),
    }


def _safe_int(value, min_val: int, max_val: int) -> int:
    """안전한 int 변환 + 범위 클리핑"""
    try:
        return int(max(min_val, min(max_val, int(value))))
    except (TypeError, ValueError):
        return 0
