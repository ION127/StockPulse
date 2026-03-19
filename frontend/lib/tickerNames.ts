/**
 * 티커 코드 → 기업명 매핑
 * core/stock_categories.py 기준
 */

const TICKER_NAMES: Record<string, string> = {
  // ── 반도체 ────────────────────────────────────────────────
  NVDA: 'NVIDIA',
  TSM: 'TSMC',
  AVGO: 'Broadcom',
  AMD: 'AMD',
  QCOM: 'Qualcomm',
  SMH: 'VanEck 반도체 ETF',
  SOXX: 'iShares 반도체 ETF',
  '091160': 'KODEX 반도체',
  '005930': '삼성전자',
  '000660': 'SK하이닉스',
  '042700': '한미반도체',

  // ── 기술/소프트웨어 ───────────────────────────────────────
  MSFT: 'Microsoft',
  AAPL: 'Apple',
  GOOGL: 'Alphabet',
  META: 'Meta',
  AMZN: 'Amazon',
  XLK: 'SPDR 기술 ETF',
  QQQ: 'Nasdaq-100 ETF',
  '098560': 'KODEX IT',
  '035420': 'NAVER',
  '035720': '카카오',
  '259960': '크래프톤',

  // ── 금융 ──────────────────────────────────────────────────
  JPM: 'JPMorgan',
  BAC: 'Bank of America',
  GS: 'Goldman Sachs',
  V: 'Visa',
  MA: 'Mastercard',
  XLF: 'SPDR 금융 ETF',
  KRE: 'SPDR 지역은행 ETF',
  '091170': 'KODEX 은행',
  '105560': 'KB금융',
  '055550': '신한지주',
  '086790': '하나금융지주',

  // ── 에너지 ────────────────────────────────────────────────
  XOM: 'ExxonMobil',
  CVX: 'Chevron',
  COP: 'ConocoPhillips',
  SLB: 'SLB',
  EOG: 'EOG Resources',
  XLE: 'SPDR 에너지 ETF',
  XOP: 'SPDR 석유가스 ETF',
  '117460': 'KODEX 에너지화학',
  '010950': 'S-Oil',
  '096770': 'SK이노베이션',
  '267250': 'HD현대중공업',

  // ── 헬스케어/바이오 ───────────────────────────────────────
  UNH: 'UnitedHealth',
  LLY: 'Eli Lilly',
  JNJ: 'Johnson & Johnson',
  ABBV: 'AbbVie',
  MRK: 'Merck',
  XLV: 'SPDR 헬스케어 ETF',
  IBB: 'iShares 바이오텍 ETF',
  '244580': 'KODEX 바이오',
  '207940': '삼성바이오로직스',
  '068270': '셀트리온',
  '326030': 'SK바이오팜',

  // ── 전기차/배터리 ─────────────────────────────────────────
  TSLA: 'Tesla',
  GM: 'General Motors',
  F: 'Ford',
  RIVN: 'Rivian',
  ALB: 'Albemarle',
  LIT: 'Global X 리튬배터리 ETF',
  DRIV: 'Global X EV ETF',
  '305720': 'KODEX 2차전지산업',
  '373220': 'LG에너지솔루션',
  '006400': '삼성SDI',
  '051910': 'LG화학',

  // ── 방산/항공우주 ─────────────────────────────────────────
  LMT: 'Lockheed Martin',
  RTX: 'RTX Corp',
  NOC: 'Northrop Grumman',
  GD: 'General Dynamics',
  BA: 'Boeing',
  ITA: 'iShares 방산 ETF',
  XAR: 'SPDR 방산 ETF',
  '475050': 'TIGER 우주방산',
  '047810': '한국항공우주',
  '012450': '한화에어로스페이스',
  '000120': 'CJ대한통운',

  // ── 소재/철강 ─────────────────────────────────────────────
  LIN: 'Linde',
  FCX: 'Freeport-McMoRan',
  NUE: 'Nucor',
  APD: 'Air Products',
  SHW: 'Sherwin-Williams',
  XLB: 'SPDR 소재 ETF',
  PICK: 'iShares 광업 ETF',
  '138540': 'KODEX 철강',
  '005490': 'POSCO홀딩스',
  '004020': '현대제철',
  '010130': '고려아연',

  // ── 부동산/리츠 ───────────────────────────────────────────
  AMT: 'American Tower',
  PLD: 'Prologis',
  EQIX: 'Equinix',
  SPG: 'Simon Property',
  O: 'Realty Income',
  XLRE: 'SPDR 부동산 ETF',
  VNQ: 'Vanguard 리츠 ETF',
  '352560': 'TIGER 리츠부동산인프라',
  '000720': '현대건설',
  '028260': '삼성물산',
  '047040': '대우건설',

  // ── 소비재 ────────────────────────────────────────────────
  HD: 'Home Depot',
  WMT: 'Walmart',
  COST: 'Costco',
  XLY: 'SPDR 소비재 ETF',
  XLP: 'SPDR 필수소비재 ETF',
  '266390': 'KODEX 200 중소형',
  '023530': '롯데쇼핑',
  '139480': '이마트',
  '004170': '신세계',
}

/**
 * 티커 코드로 기업명을 반환합니다.
 * 매핑이 없으면 원래 티커 코드를 그대로 반환합니다.
 */
export function getCompanyName(ticker: string): string {
  return TICKER_NAMES[ticker] ?? ticker
}

/**
 * 티커 코드가 기업명 매핑에 있는지 확인합니다.
 */
export function hasCompanyName(ticker: string): boolean {
  return ticker in TICKER_NAMES
}
