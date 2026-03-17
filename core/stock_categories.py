"""
섹터별 ETF + 시가총액 상위 종목 정의

설계 원칙:
  - ETF     : 섹터 전체의 방향성 (체온계) — ETF가 움직이면 섹터 이벤트
  - 개별종목 : 섹터 내 확인 신호 + 증폭 — 상위 3~5개 시가총액 종목만

US ETF 출처  : SPDR 섹터 ETF(XL*), iShares, VanEck, Global X
KR ETF 출처  : KODEX(삼성자산), TIGER(미래에셋), KINDEX(한국투자)
"""

STOCK_CATEGORIES: dict[str, dict] = {

    # ── 1. 반도체 ────────────────────────────────────────────────────────────
    "반도체 (Semiconductor)": {
        "etfs_us": ["SMH", "SOXX"],          # VanEck 반도체, iShares 반도체
        "etfs_kr": ["091160"],               # KODEX 반도체
        "tickers_us": ["NVDA", "TSM", "AVGO", "AMD", "QCOM"],
        "tickers_kr": ["005930", "000660", "042700"],   # 삼성전자, SK하이닉스, 한미반도체
        "keywords_en": ["semiconductor", "chip", "GPU", "AI chip", "memory", "foundry", "wafer"],
        "keywords_kr": ["반도체", "칩", "GPU", "파운드리", "낸드", "D램", "삼성전자", "하이닉스"],
    },

    # ── 2. 기술/소프트웨어 ────────────────────────────────────────────────────
    "기술/소프트웨어 (Technology)": {
        "etfs_us": ["XLK", "QQQ"],           # SPDR 기술, Nasdaq-100
        "etfs_kr": ["098560"],               # KODEX IT
        "tickers_us": ["MSFT", "AAPL", "GOOGL", "META", "AMZN"],
        "tickers_kr": ["035420", "035720", "259960"],   # NAVER, 카카오, 크래프톤
        "keywords_en": ["software", "cloud", "AI", "platform", "big tech", "antitrust", "regulation"],
        "keywords_kr": ["소프트웨어", "클라우드", "AI", "플랫폼", "빅테크", "네이버", "카카오"],
    },

    # ── 3. 금융 ──────────────────────────────────────────────────────────────
    "금융 (Financials)": {
        "etfs_us": ["XLF", "KRE"],           # SPDR 금융, SPDR 지역은행
        "etfs_kr": ["091170"],               # KODEX 은행
        "tickers_us": ["JPM", "BAC", "GS", "V", "MA"],
        "tickers_kr": ["105560", "055550", "086790"],   # KB금융, 신한지주, 하나금융
        "keywords_en": ["bank", "Fed", "interest rate", "inflation", "financial", "credit", "Basel"],
        "keywords_kr": ["금융", "금리", "한국은행", "연준", "인플레이션", "은행", "예금"],
    },

    # ── 4. 에너지 ────────────────────────────────────────────────────────────
    "에너지 (Energy)": {
        "etfs_us": ["XLE", "XOP"],           # SPDR 에너지, SPDR 석유가스탐사
        "etfs_kr": ["117460"],               # KODEX 에너지화학
        "tickers_us": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "tickers_kr": ["010950", "096770", "267250"],   # S-Oil, SK이노베이션, HD현대중공업
        "keywords_en": ["oil", "gas", "crude", "OPEC", "energy", "refinery", "LNG", "WTI"],
        "keywords_kr": ["원유", "정유", "OPEC", "에너지", "가스", "LNG", "WTI", "유가"],
    },

    # ── 5. 헬스케어/바이오 ────────────────────────────────────────────────────
    "헬스케어/바이오 (Healthcare)": {
        "etfs_us": ["XLV", "IBB"],           # SPDR 헬스케어, iShares 바이오테크
        "etfs_kr": ["244580"],               # KODEX 바이오
        "tickers_us": ["UNH", "LLY", "JNJ", "ABBV", "MRK"],
        "tickers_kr": ["207940", "068270", "326030"],   # 삼성바이오로직스, 셀트리온, SK바이오팜
        "keywords_en": ["FDA", "drug approval", "clinical trial", "biotech", "pharma", "vaccine", "healthcare"],
        "keywords_kr": ["바이오", "신약", "임상", "FDA", "식약처", "셀트리온", "삼성바이오"],
    },

    # ── 6. 전기차/배터리 ──────────────────────────────────────────────────────
    "전기차/배터리 (EV & Battery)": {
        "etfs_us": ["LIT", "DRIV"],          # Global X 리튬배터리, Global X 자율주행EV
        "etfs_kr": ["305720"],               # KODEX 2차전지산업
        "tickers_us": ["TSLA", "GM", "F", "RIVN", "ALB"],
        "tickers_kr": ["373220", "006400", "051910"],   # LG에너지솔루션, 삼성SDI, LG화학
        "keywords_en": ["EV", "electric vehicle", "battery", "lithium", "charging", "Tesla", "IRA"],
        "keywords_kr": ["전기차", "배터리", "리튬", "충전", "LG에너지", "삼성SDI", "K배터리"],
    },

    # ── 7. 방산/항공우주 ──────────────────────────────────────────────────────
    "방산/항공우주 (Defense & Aerospace)": {
        "etfs_us": ["ITA", "XAR"],           # iShares 항공우주방산, SPDR 항공우주방산
        "etfs_kr": ["475050"],               # TIGER 우주방산
        "tickers_us": ["LMT", "RTX", "NOC", "GD", "BA"],
        "tickers_kr": ["047810", "012450", "000120"],   # 한국항공우주, 한화에어로스페이스, CJ대한통운
        "keywords_en": ["defense", "military", "NATO", "missile", "aerospace", "war", "geopolitical"],
        "keywords_kr": ["방산", "무기", "미사일", "NATO", "전쟁", "지정학", "항공우주", "한화"],
    },

    # ── 8. 소재/철강 ─────────────────────────────────────────────────────────
    "소재/철강 (Materials)": {
        "etfs_us": ["XLB", "PICK"],          # SPDR 소재, iShares 광업금속
        "etfs_kr": ["138540"],               # KODEX 철강
        "tickers_us": ["LIN", "FCX", "NUE", "APD", "SHW"],
        "tickers_kr": ["005490", "004020", "010130"],   # POSCO홀딩스, 현대제철, 고려아연
        "keywords_en": ["steel", "copper", "iron", "materials", "tariff", "mining", "aluminum"],
        "keywords_kr": ["철강", "구리", "포스코", "고려아연", "관세", "광물", "소재"],
    },

    # ── 9. 부동산/리츠 ───────────────────────────────────────────────────────
    "부동산/리츠 (Real Estate)": {
        "etfs_us": ["XLRE", "VNQ"],          # SPDR 부동산, Vanguard 리츠
        "etfs_kr": ["352560"],               # TIGER 리츠부동산인프라
        "tickers_us": ["AMT", "PLD", "EQIX", "SPG", "O"],
        "tickers_kr": ["000720", "028260", "047040"],   # 현대건설, 삼성물산, 대우건설
        "keywords_en": ["REIT", "real estate", "mortgage", "housing", "rate", "construction"],
        "keywords_kr": ["리츠", "부동산", "아파트", "건설", "금리", "모기지", "분양"],
    },

    # ── 10. 소비재 ───────────────────────────────────────────────────────────
    "소비재 (Consumer)": {
        "etfs_us": ["XLY", "XLP"],           # SPDR 경기소비재, SPDR 필수소비재
        "etfs_kr": ["266390"],               # KODEX 200 중소형
        "tickers_us": ["AMZN", "TSLA", "HD", "WMT", "COST"],
        "tickers_kr": ["023530", "139480", "004170"],   # 롯데쇼핑, 이마트, 신세계
        "keywords_en": ["consumer", "retail", "spending", "inflation", "tariff", "import"],
        "keywords_kr": ["소비재", "유통", "소비", "물가", "관세", "이마트", "롯데"],
    },
}


# ── 헬퍼 함수 ────────────────────────────────────────────────────────────────

def _all_etfs_us() -> set[str]:
    tickers = set()
    for cat in STOCK_CATEGORIES.values():
        tickers.update(cat.get("etfs_us", []))
    return tickers


def _all_etfs_kr() -> set[str]:
    tickers = set()
    for cat in STOCK_CATEGORIES.values():
        tickers.update(cat.get("etfs_kr", []))
    return tickers


# 캐시
_ETF_US: set[str] = _all_etfs_us()
_ETF_KR: set[str] = _all_etfs_kr()
_ALL_ETF: set[str] = _ETF_US | {f"KR:{c}" for c in _ETF_KR}


def get_all_us_tickers() -> list[str]:
    """ETF + 개별종목 포함, 모든 미국 티커 (중복 제거)."""
    tickers: set[str] = set()
    for cat in STOCK_CATEGORIES.values():
        tickers.update(cat.get("etfs_us", []))
        tickers.update(cat.get("tickers_us", []))
    return list(tickers)


def get_all_kr_tickers() -> list[str]:
    """ETF + 개별종목 포함, 모든 한국 종목코드 (중복 제거)."""
    tickers: set[str] = set()
    for cat in STOCK_CATEGORIES.values():
        tickers.update(cat.get("etfs_kr", []))
        tickers.update(cat.get("tickers_kr", []))
    return list(tickers)


def is_etf(ticker: str) -> bool:
    """해당 티커가 ETF인지 여부 (KR 포함)."""
    return ticker in _ETF_US or ticker in _ETF_KR or ticker in _ALL_ETF


def get_ticker_category(ticker: str) -> str | None:
    """티커가 속한 카테고리 반환 (ETF 포함)."""
    bare = ticker.replace("KR:", "")
    for name, data in STOCK_CATEGORIES.items():
        if (ticker in data.get("etfs_us", [])
                or ticker in data.get("tickers_us", [])
                or bare in data.get("etfs_kr", [])
                or bare in data.get("tickers_kr", [])):
            return name
    return None


def get_category_keywords(category_name: str) -> dict:
    """카테고리의 뉴스 검색 키워드 반환."""
    cat = STOCK_CATEGORIES.get(category_name, {})
    return {
        "en": cat.get("keywords_en", []),
        "kr": cat.get("keywords_kr", []),
    }
