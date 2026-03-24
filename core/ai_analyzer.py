"""
Groq API를 사용한 주식 이상값 분석 모듈
영문/한국어 동시 분석 결과 제공
무료 티어: llama-3.3-70b-versatile (분당 30회, 하루 14,400회)
"""

import os
import time
import logging
from groq import Groq

from core.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

# Groq API용 Circuit Breaker (5회 연속 실패 시 60초 차단)
_groq_cb = CircuitBreaker(name="groq", failure_threshold=5, recovery_timeout=60.0)

_SYSTEM_INSTRUCTION = (
    "You are a professional financial analyst and market intelligence expert. "
    "You analyze stock price anomalies (sudden spikes or drops) and identify their root causes "
    "using news data from both English and Korean sources. "
    "Your analysis must be provided in BOTH languages: Korean (한국어) and English. "
    "Be concise but insightful. Focus on: root causes, global/macro context, "
    "sector-wide implications, and key catalysts. "
    "Format your response exactly as specified."
)

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
    return _client


# 분당 30회 제한 → 호출 사이 최소 2초 간격
_MIN_INTERVAL_SEC = 2
_last_call_time = 0.0


def _call_groq(prompt: str, max_tokens: int = 3000, retries: int = 3) -> str:
    """Groq API 호출 공통 함수 (속도 제한 + 자동 재시도)"""
    global _last_call_time

    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)

    def _single_call() -> str:
        response = _get_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    for attempt in range(retries):
        try:
            _last_call_time = time.time()
            # Circuit Breaker를 통해 호출 — OPEN 상태면 CircuitOpenError 발생
            return _groq_cb.call(_single_call)
        except CircuitOpenError:
            raise  # 상위로 전파 (ai-analyzer main에서 DLQ 처리)
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < retries - 1:
                wait = 60
                import re
                m = re.search(r"try again in ([\d.]+)s", err)
                if m:
                    wait = int(float(m.group(1))) + 2
                logger.warning(f"429 속도 제한 → {wait}초 후 재시도 ({attempt+1}/{retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Groq API 재시도 초과")


_EVENT_FOCUS = {
    "INDIVIDUAL": (
        "This appears to be a COMPANY-SPECIFIC event (only this stock moved unusually). "
        "Focus your analysis on company-level causes: earnings, contracts, leadership, lawsuits, product news, etc."
    ),
    "SECTOR": (
        "This appears to be a SECTOR-WIDE event (multiple stocks in this sector moved together). "
        "Focus on sector-level causes: regulation changes, commodity prices, industry news, government policy, etc."
    ),
    "MARKET": (
        "This appears to be a MARKET-WIDE / MACRO event (multiple sectors moved together). "
        "Focus on macro causes: Fed decisions, geopolitical events, trade policy, inflation data, global crisis, etc."
    ),
}


def analyze_anomaly(
    ticker: str,
    category: str,
    return_pct: float,
    direction: str,
    date: str,
    close_price: float,
    news_text: str,
    event_type: str = "INDIVIDUAL",
    sector_peer_count: int = 1,
    moving_sector_count: int = 1,
) -> dict[str, str]:
    """
    Groq API로 단일 종목 이상값 분석
    반환: {"ko": "한국어 분석", "en": "영어 분석"}
    """
    event_focus = _EVENT_FOCUS.get(event_type, _EVENT_FOCUS["INDIVIDUAL"])
    event_type_kr = {"INDIVIDUAL": "개별 이벤트", "SECTOR": "섹터 이벤트", "MARKET": "시장 전체 이벤트"}.get(event_type, "")

    prompt = f"""
Analyze the following stock price anomaly:

**Stock:** {ticker}
**Category/Sector:** {category}
**Date:** {date}
**Price Change:** {return_pct:+.2f}% ({direction})
**Closing Price:** {close_price}
**Event Classification:** {event_type} ({event_type_kr})
  - Same-sector stocks moving together: {sector_peer_count}
  - Total sectors moving in same direction: {moving_sector_count}

**Analysis Focus:** {event_focus}

**Related News (English & Korean):**
{news_text if news_text else "No news data available."}

Please provide your analysis in the following exact format:

---[한국어 분석]---
**종목:** {ticker} ({category})
**이벤트:** {date} {direction} {return_pct:+.2f}%

**원인 분석:**
[3-5줄로 주가 급등/급락의 주요 원인 설명]

**섹터 영향:**
[이 섹터 전반에 미치는 영향 2-3줄]

**투자자 시각:**
[이 이벤트의 의미와 향후 전망 2-3줄]

---[English Analysis]---
**Stock:** {ticker} ({category})
**Event:** {direction} {return_pct:+.2f}% on {date}

**Root Cause Analysis:**
[3-5 lines explaining the primary causes]

**Sector Impact:**
[2-3 lines on broader sector implications]

**Investor Perspective:**
[2-3 lines on significance and outlook]
"""

    try:
        full_text = _call_groq(prompt, max_tokens=3000)

        ko_part = ""
        en_part = ""

        if "---[한국어 분석]---" in full_text and "---[English Analysis]---" in full_text:
            parts = full_text.split("---[English Analysis]---")
            ko_part = parts[0].replace("---[한국어 분석]---", "").strip()
            en_part = parts[1].strip() if len(parts) > 1 else ""
        elif "---[한국어 분석]---" in full_text:
            ko_part = full_text.replace("---[한국어 분석]---", "").strip()
            en_part = ""
        elif "---[English Analysis]---" in full_text:
            ko_part = ""
            en_part = full_text.replace("---[English Analysis]---", "").strip()
        else:
            ko_part = full_text
            en_part = ""

        return {"ko": ko_part, "en": en_part}

    except CircuitOpenError:
        raise  # ai-analyzer main.py에서 DLQ 처리
    except Exception as e:
        logger.error(f"Groq API 오류 ({ticker}): {e}")
        return {
            "ko": f"분석 실패: {e}",
            "en": f"Analysis failed: {e}",
        }


def analyze_sector_trends(sector_anomalies: dict[str, list[dict]]) -> dict[str, str]:
    """
    섹터별 전체 트렌드 분석 (여러 종목의 이상값을 묶어서 분석)
    세계가 어느 섹터에 관심을 가지는지 파악
    """
    if not sector_anomalies:
        return {"ko": "이상값 없음", "en": "No anomalies detected"}

    summary_lines = []
    for sector, anomalies in sector_anomalies.items():
        if not anomalies:
            continue
        avg_change = sum(a["return_pct"] for a in anomalies) / len(anomalies)
        max_change = max(anomalies, key=lambda x: abs(x["return_pct"]))
        summary_lines.append(
            f"- {sector}: {len(anomalies)}개 종목 이상값, "
            f"평균 변동 {avg_change:+.1f}%, "
            f"최대 {max_change['ticker']} {max_change['return_pct']:+.1f}%"
        )

    sector_summary = "\n".join(summary_lines)

    prompt = f"""
Today's stock market anomaly summary by sector:

{sector_summary}

Based on this data, analyze:
1. Which sectors are getting the most global attention?
2. What macro events or trends might be driving this?
3. What does this tell us about global investment sentiment?

Respond in this exact format:

---[한국어 종합 분석]---
**오늘의 시장 핫 섹터:**
[가장 주목받는 섹터 2-3개와 이유]

**글로벌 관심 원인:**
[세계적으로 이 섹터들이 주목받는 거시적 원인 3-5줄]

**투자 시장 분위기:**
[현재 글로벌 투자 심리와 트렌드 2-3줄]

---[English Macro Analysis]---
**Today's Hot Sectors:**
[Top 2-3 sectors drawing attention and why]

**Global Drivers:**
[3-5 lines on macro events driving these sectors]

**Market Sentiment:**
[2-3 lines on current global investment sentiment]
"""

    try:
        full_text = _call_groq(prompt, max_tokens=1200)

        ko_part = ""
        en_part = ""

        if "---[한국어 종합 분석]---" in full_text and "---[English Macro Analysis]---" in full_text:
            parts = full_text.split("---[English Macro Analysis]---")
            ko_part = parts[0].replace("---[한국어 종합 분석]---", "").strip()
            en_part = parts[1].strip() if len(parts) > 1 else ""
        elif "---[한국어 종합 분석]---" in full_text:
            ko_part = full_text.replace("---[한국어 종합 분석]---", "").strip()
            en_part = ""
        elif "---[English Macro Analysis]---" in full_text:
            ko_part = ""
            en_part = full_text.replace("---[English Macro Analysis]---", "").strip()
        else:
            ko_part = full_text
            en_part = ""

        return {"ko": ko_part, "en": en_part}

    except Exception as e:
        logger.error(f"섹터 트렌드 분석 오류: {e}")
        return {"ko": f"분석 실패: {e}", "en": f"Analysis failed: {e}"}
