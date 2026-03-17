"""
주식 카테고리 정의 - 섹터별 종목 목록
글로벌(미국) 주식과 한국 주식을 함께 관리
"""

STOCK_CATEGORIES = {
    "드론/방산 (Drone/Defense)": {
        "tickers_us": ["AVAV", "KTOS", "AXON", "LMT", "RTX", "NOC", "BA", "AIR"],
        "tickers_kr": ["047810", "012450", "007570"],  # 한국항공우주, 한화에어로스페이스, 방산
        "keywords_en": ["drone", "defense", "military", "UAV", "aerospace"],
        "keywords_kr": ["드론", "방산", "무인기", "항공우주", "군수"],
    },
    "에너지 (Energy)": {
        "tickers_us": ["XOM", "CVX", "COP", "SLB", "BP", "SHEL", "NEE", "ENPH", "FSLR"],
        "tickers_kr": ["015760", "267250", "036460"],  # 한국전력, 현대중공업, 한국가스공사
        "keywords_en": ["energy", "oil", "gas", "solar", "wind", "renewable", "crude", "OPEC"],
        "keywords_kr": ["에너지", "원유", "가스", "태양광", "풍력", "신재생", "한전"],
    },
    "철강/소재 (Steel/Materials)": {
        "tickers_us": ["X", "NUE", "STLD", "CLF", "MT", "FCX", "AA"],
        "tickers_kr": ["005490", "004020", "010130"],  # POSCO, 현대제철, 고려아연
        "keywords_en": ["steel", "iron", "metals", "copper", "aluminum", "mining", "tariff"],
        "keywords_kr": ["철강", "포스코", "철광석", "구리", "알루미늄", "광물", "관세"],
    },
    "반도체 (Semiconductor)": {
        "tickers_us": ["NVDA", "AMD", "INTC", "TSM", "QCOM", "AVGO", "MU", "AMAT"],
        "tickers_kr": ["005930", "000660", "042700"],  # 삼성전자, SK하이닉스, 한미반도체
        "keywords_en": ["semiconductor", "chip", "AI chip", "GPU", "memory", "foundry"],
        "keywords_kr": ["반도체", "칩", "엔비디아", "삼성", "하이닉스", "파운드리"],
    },
    "AI/빅테크 (AI/Big Tech)": {
        "tickers_us": ["NVDA", "MSFT", "GOOGL", "META", "AMZN", "AAPL", "TSLA", "PLTR"],
        "tickers_kr": ["035420", "035720", "259960"],  # NAVER, 카카오, 크래프톤
        "keywords_en": ["artificial intelligence", "AI", "machine learning", "LLM", "OpenAI", "ChatGPT"],
        "keywords_kr": ["인공지능", "AI", "머신러닝", "챗GPT", "네이버", "카카오"],
    },
    "바이오/헬스케어 (Bio/Healthcare)": {
        "tickers_us": ["JNJ", "PFE", "MRNA", "ABBV", "UNH", "ISRG", "REGN"],
        "tickers_kr": ["207940", "068270", "326030"],  # 삼성바이오로직스, 셀트리온, SK바이오팜
        "keywords_en": ["biotech", "pharma", "FDA approval", "clinical trial", "drug", "vaccine"],
        "keywords_kr": ["바이오", "제약", "임상", "신약", "식약처", "셀트리온"],
    },
    "전기차/배터리 (EV/Battery)": {
        "tickers_us": ["TSLA", "RIVN", "LCID", "GM", "F", "CHPT", "ALB", "LAC"],
        "tickers_kr": ["051910", "373220", "006400"],  # LG화학, LG에너지솔루션, 삼성SDI
        "keywords_en": ["electric vehicle", "EV", "battery", "lithium", "charging", "Tesla"],
        "keywords_kr": ["전기차", "배터리", "리튬", "충전", "LG에너지", "삼성SDI"],
    },
    "금융 (Finance)": {
        "tickers_us": ["JPM", "BAC", "GS", "MS", "BLK", "V", "MA", "PYPL"],
        "tickers_kr": ["105560", "055550", "086790"],  # KB금융, 신한지주, 하나금융
        "keywords_en": ["bank", "interest rate", "Fed", "inflation", "financial", "credit"],
        "keywords_kr": ["금융", "금리", "한국은행", "인플레이션", "은행", "금융위기"],
    },
    "부동산/건설 (Real Estate/Construction)": {
        "tickers_us": ["AMT", "PLD", "CCI", "SPG", "O", "DRE"],
        "tickers_kr": ["000720", "028050", "047040"],  # 현대건설, 삼성물산, 대우건설
        "keywords_en": ["real estate", "housing", "construction", "REIT", "mortgage"],
        "keywords_kr": ["부동산", "건설", "아파트", "주택", "금리", "분양"],
    },
}

def get_all_us_tickers() -> list[str]:
    """모든 미국 주식 티커 반환 (중복 제거)"""
    tickers = set()
    for category in STOCK_CATEGORIES.values():
        tickers.update(category.get("tickers_us", []))
    return list(tickers)

def get_all_kr_tickers() -> list[str]:
    """모든 한국 주식 코드 반환 (중복 제거)"""
    tickers = set()
    for category in STOCK_CATEGORIES.values():
        tickers.update(category.get("tickers_kr", []))
    return list(tickers)

def get_ticker_category(ticker: str) -> str | None:
    """티커가 속한 카테고리 반환"""
    for category_name, data in STOCK_CATEGORIES.items():
        if ticker in data.get("tickers_us", []) or ticker in data.get("tickers_kr", []):
            return category_name
    return None

def get_category_keywords(category_name: str) -> dict:
    """카테고리의 뉴스 검색 키워드 반환"""
    return {
        "en": STOCK_CATEGORIES[category_name].get("keywords_en", []),
        "kr": STOCK_CATEGORIES[category_name].get("keywords_kr", []),
    }
