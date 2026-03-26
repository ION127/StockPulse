"""
피처 엔지니어링 모듈 v3
- OHLCV → 기술적 지표 (중복/과적합 제거 후 ~28개)
- KRX 수급: 외국인/기관/개인, 공매도잔고, 대차잔고(공매도 선행), 프로그램 매매
- DART 재무비율 (Look-ahead Bias 방지: 공시일 기준 lag 적용)
- DART 공시 이벤트 (날짜 인덱스 기반)
- 매크로 지표: VIX, VKOSPI, 환율, 유가, 금리차, 투자자예탁금
- 시장 국면 (Regime) / Google Trends
- BOK ECOS: 기준금리 시계열, 투자자예탁금 (API 키 있을 때만)

[오버피팅 방지 원칙]
- 수학적 중복 피처 제거 (williams_r = stoch_k - 100 등)
- 단일 스칼라를 전체 행에 적용하는 피처 제거 (look-ahead bias)
- 상관관계 높은 중복 지표 제거 (rsi_7 vs rsi_14 등)
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from core.collectors.krx_collector import (
    get_investor_trading, get_short_selling, get_market_trading,
    get_credit_balance, get_program_trading, get_ohlcv,
    get_vkospi, get_lending_balance,
)
from core.collectors.macro_collector import (
    get_market_indices, get_fear_greed, get_us_economic_calendar,
    get_bok_base_rate_series, get_bok_investor_deposit,
)
from core.collectors.dart_collector import (
    get_financial_ratios_with_lag, get_disclosure_events,
)
from core.collectors.sentiment_collector import get_google_trends
from core.regime_detector import add_regime_features, get_kospi_regime

logger = logging.getLogger(__name__)

# Look-ahead bias 방지: 재무 데이터 최소 lag (일)
_FINANCIAL_LAG_DAYS = 60


# ── 기술적 지표 계산 ───────────────────────────────────────────────────────

def compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV DataFrame → 기술적 지표 추가 (약 35개 컬럼)"""
    df = df.copy()
    close  = df["close"].astype(float)
    high   = df["high"].astype(float)
    low    = df["low"].astype(float)
    volume = df["volume"].astype(float)

    # ── RSI ──────────────────────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta.clip(upper=0))
    df["rsi_14"] = 100 - 100 / (1 + gain.ewm(com=13, adjust=False).mean()
                                  / (loss.ewm(com=13, adjust=False).mean() + 1e-10))
    # rsi_7 제거: rsi_14와 상관관계 ~0.85, 과적합 위험

    # ── MACD ─────────────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    # ── 볼린저 밴드 ──────────────────────────────────────────────────────
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_up = sma20 + 2 * std20
    bb_lo = sma20 - 2 * std20
    df["bb_position"] = (close - bb_lo) / (bb_up - bb_lo + 1e-10)
    df["bb_width"]    = (bb_up - bb_lo) / (sma20 + 1e-10)

    # ── 이동평균 대비 ─────────────────────────────────────────────────────
    # 단기(5)/중기(20)/장기(60) 3개만 유지 — sma10은 sma5/20 사이, sma120은 sma60과 중복
    for p in [5, 20, 60]:
        sma = close.rolling(p, min_periods=p // 2).mean()
        df[f"price_sma{p}_ratio"] = close / (sma + 1e-10) - 1

    # ── ATR ──────────────────────────────────────────────────────────────
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"]    = tr.ewm(com=13, adjust=False).mean()
    df["atr_ratio"] = df["atr_14"] / (close + 1e-10)

    # ── 거래량 ───────────────────────────────────────────────────────────
    vol_ma20 = volume.rolling(20).mean()
    df["vol_ratio"]    = volume / (vol_ma20 + 1e-10)
    # vol_ratio_5 제거: vol_ratio(20일 기준)로 충분, 5일은 과적합 위험
    df["vol_surge"]    = (df["vol_ratio"] > 2.0).astype(int)

    # OBV
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    df["obv_ratio"] = obv / (obv.rolling(20).mean().abs() + 1e-10)

    # ── 모멘텀 ───────────────────────────────────────────────────────────
    # ret_1d 제거: 단기 노이즈 과대, 다음날 예측에 오히려 역효과
    for p in [3, 5, 10, 20, 60]:
        df[f"ret_{p}d"] = close.pct_change(p)

    # ── 변동성 ───────────────────────────────────────────────────────────
    df["vol_5d"]  = close.pct_change().rolling(5).std()
    df["vol_20d"] = close.pct_change().rolling(20).std()
    df["vol_ratio_5_20"] = df["vol_5d"] / (df["vol_20d"] + 1e-10)  # 변동성 확대 여부

    # ── 52주 위치 ─────────────────────────────────────────────────────────
    high52 = high.rolling(252, min_periods=60).max()
    low52  = low.rolling(252, min_periods=60).min()
    df["pos_52w"] = (close - low52) / (high52 - low52 + 1e-10)
    # dist_high, dist_low 제거: pos_52w 하나로 동일 정보 표현 가능

    # ── 스토캐스틱 ───────────────────────────────────────────────────────
    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    df["stoch_k"] = (close - low14) / (high14 - low14 + 1e-10) * 100
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # williams_r 제거: stoch_k와 수학적으로 동일 (williams_r = stoch_k - 100)

    # ── CCI ──────────────────────────────────────────────────────────────
    tp = (high + low + close) / 3
    df["cci_20"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std() + 1e-10)

    # ── 갭 / 캔들 ────────────────────────────────────────────────────────
    df["gap_pct"]      = (df["open"] - close.shift(1)) / (close.shift(1) + 1e-10)
    df["candle_body"]  = (close - df["open"]).abs() / (high - low + 1e-10)
    df["upper_shadow"] = (high - pd.concat([close, df["open"]], axis=1).max(axis=1)) / (high - low + 1e-10)
    df["lower_shadow"] = (pd.concat([close, df["open"]], axis=1).min(axis=1) - low) / (high - low + 1e-10)
    df["bullish_candle"] = (close > df["open"]).astype(int)

    return df


# ── Look-ahead Bias 안전 join ─────────────────────────────────────────────

def _safe_join_financial(
    features: pd.DataFrame,
    financial_data: dict,
    available_from: datetime,
) -> pd.DataFrame:
    """
    재무 데이터를 공시 가능 날짜 이후에만 피처로 합침 (Look-ahead bias 방지)
    """
    if not financial_data or available_from is None:
        return features

    df = features.copy()
    for key, val in financial_data.items():
        col = f"fin_{key}"
        # available_from 이전 날짜는 NaN으로 (미래 정보 차단)
        df[col] = np.nan
        mask = df.index >= pd.Timestamp(available_from)
        df.loc[mask, col] = val

    return df


# ── 통합 피처 매트릭스 ─────────────────────────────────────────────────────

def build_feature_matrix(
    ticker: str,
    days_back: int = 365,
    include_slow_features: bool = True,
    sector: str = "",
) -> pd.DataFrame:
    """
    모든 데이터 소스를 통합한 피처 매트릭스 생성

    Args:
        ticker            : 종목코드 (예: "KR:005930")
        days_back         : 과거 데이터 기간 (일)
        include_slow_features : 크롤링/API 느린 피처 포함 여부
        sector            : 섹터 이름 (참고용)

    Returns:
        날짜 인덱스, 모든 피처 컬럼을 포함한 DataFrame
    """
    end   = datetime.now()
    start = end - timedelta(days=days_back + 60)  # 기술적 지표 웜업 기간 포함
    start_str = start.strftime("%Y%m%d")
    end_str   = end.strftime("%Y%m%d")

    logger.info(f"[Feature] {ticker} 피처 구축 시작 ({start_str}~{end_str})")

    # ── 1. OHLCV + 기술적 지표 ────────────────────────────────────────────
    ohlcv = get_ohlcv(ticker, start_str, end_str)
    if ohlcv.empty or len(ohlcv) < 30:
        logger.warning(f"[Feature] {ticker} OHLCV 부족 ({len(ohlcv)}행)")
        return pd.DataFrame()

    features = compute_technical_indicators(ohlcv)

    # ── 2. 시장 국면 (Regime) ─────────────────────────────────────────────
    features = add_regime_features(features, use_hmm=False)

    # ── 3. KRX 수급 ──────────────────────────────────────────────────────
    investor = get_investor_trading(ticker, start_str, end_str)
    if not investor.empty:
        investor.index = pd.to_datetime(investor.index).normalize()
        features = features.join(investor, how="left")
        for col in ["foreign_net", "institution_net"]:
            if col in features.columns:
                features[f"{col}_3d"] = features[col].rolling(3).sum()
                features[f"{col}_5d"] = features[col].rolling(5).sum()
                # 수급 모멘텀: 최근 3일 vs 20일 평균
                features[f"{col}_momentum"] = (
                    features[col].rolling(3).mean()
                    / (features[col].rolling(20).mean().abs() + 1e-10)
                )

    short_df = get_short_selling(ticker, start_str, end_str)
    if not short_df.empty:
        short_df.index = pd.to_datetime(short_df.index).normalize()
        features = features.join(short_df, how="left")

    mkt = get_market_trading(start_str, end_str)
    if not mkt.empty:
        mkt.index = pd.to_datetime(mkt.index).normalize()
        features = features.join(mkt, how="left")

    # ── 4. 신용잔고 (개인 레버리지) ─────────────────────────────────────
    credit = get_credit_balance(ticker, start_str, end_str)
    if not credit.empty:
        credit.index = pd.to_datetime(credit.index).normalize()
        features = features.join(credit, how="left")

    # ── 5. 프로그램 매매 ─────────────────────────────────────────────────
    program = get_program_trading(start_str, end_str)
    if not program.empty:
        program.index = pd.to_datetime(program.index).normalize()
        features = features.join(program, how="left")

    # ── 5-A. 대차잔고 (공매도 선행지표) ─────────────────────────────────
    # 공매도 잔고보다 1~2주 앞서 움직이는 선행 지표
    lending = get_lending_balance(ticker, start_str, end_str)
    if not lending.empty:
        lending.index = pd.to_datetime(lending.index).normalize()
        features = features.join(lending, how="left")

    # ── 6. 매크로 지표 ────────────────────────────────────────────────────
    macro = get_market_indices(days_back=days_back + 60)
    if not macro.empty:
        macro.index = macro.index.normalize()
        features = features.join(macro, how="left")

        # KOSPI 국면을 별도 컬럼으로 추가
        kospi_regime = get_kospi_regime(macro)
        if kospi_regime is not None:
            kospi_regime.index = pd.to_datetime(kospi_regime.index).normalize()
            features["kospi_regime"] = kospi_regime.reindex(features.index).ffill()

    fear_greed = get_fear_greed()
    if fear_greed is not None:
        features["fear_greed"] = fear_greed

    # ── 6-A. VKOSPI (한국판 VIX) ─────────────────────────────────────────
    # 미국 VIX보다 한국 시장에 직접적인 공포/변동성 지수
    vkospi_df = get_vkospi(start_str, end_str)
    if not vkospi_df.empty:
        vkospi_df.index = pd.to_datetime(vkospi_df.index).normalize()
        features = features.join(vkospi_df, how="left")

    # ── 6-B. BOK 기준금리 시계열 (BOK_API_KEY 있을 때만) ─────────────────
    bok_rate = get_bok_base_rate_series(days_back=days_back + 60)
    if not bok_rate.empty:
        bok_rate.index = pd.to_datetime(bok_rate.index).normalize()
        features = features.join(bok_rate, how="left")

    # ── 6-C. 투자자예탁금 (BOK_API_KEY 있을 때만) ────────────────────────
    # 예탁금 증가 = 매수 대기 자금 유입 → 1~2주 선행 상승 신호
    deposit_df = get_bok_investor_deposit(days_back=days_back + 60)
    if not deposit_df.empty:
        deposit_df.index = pd.to_datetime(deposit_df.index).normalize()
        features = features.join(deposit_df, how="left")

    cal = get_us_economic_calendar()
    features["is_fomc_month"]  = int(cal.get("is_fomc_month", False))
    features["is_quarter_end"] = int(cal.get("is_quarter_end", False))

    # ── 7. DART 공시 이벤트 (Look-ahead bias 없음: 날짜 인덱스 기반) ────────
    if include_slow_features:
        disclosures = get_disclosure_events(ticker, days_back=days_back)
        if not disclosures.empty:
            disclosures.index = pd.to_datetime(disclosures.index).normalize()
            features = features.join(disclosures, how="left")

        # ── 8. DART 재무비율 (Look-ahead bias 방지: lag 적용) ─────────────
        fin_result = get_financial_ratios_with_lag(ticker)
        features = _safe_join_financial(
            features,
            fin_result.get("data", {}),
            fin_result.get("available_from"),
        )

        # earnings_surprise, analyst_upside 제거:
        # 단일 현재값 → 모든 과거 행에 동일 적용 = look-ahead bias
        # 분기별 시계열로 구현하지 않는 한 학습 데이터에서 제외

        # ── 11. Google Trends ─────────────────────────────────────────────
        clean = ticker.replace("KR:", "").replace(".KS", "").replace(".KQ", "")
        trends = get_google_trends([clean], days_back=min(days_back, 90))
        if not trends.empty:
            trends.columns = [f"trend_{c}" for c in trends.columns]
            trends.index = pd.to_datetime(trends.index).normalize()
            features = features.join(trends, how="left")

        # naver_sentiment, discussion_count, avg_likes 제거:
        # 현재 시점 단일값 → 모든 과거 행에 동일 적용 = 시간 신호 없음 + look-ahead bias
        # LLM 피처도 동일 이유로 학습 데이터에서 제거
        pass

    # ── 결측값 처리 ────────────────────────────────────────────────────────
    # 수급/매크로: forward fill
    ffill_cols = [c for c in features.columns if any(
        k in c for k in [
            "foreign", "institution", "short", "mkt_", "credit",
            "program", "vix", "usd_krw", "oil", "kospi", "nasdaq",
            "yield", "dxy", "gold", "fear_greed",
            "lending", "vkospi", "bok_", "deposit",
        ]
    )]
    if ffill_cols:
        features[ffill_cols] = features[ffill_cols].ffill()

    # 재무 데이터: look-ahead lag로 생긴 초반 NaN → 0 처리
    fin_cols = [c for c in features.columns if c.startswith("fin_")]
    if fin_cols:
        features[fin_cols] = features[fin_cols].fillna(0)

    # 나머지 NaN: 중앙값
    num_cols = features.select_dtypes(include=[np.number]).columns
    features[num_cols] = features[num_cols].fillna(features[num_cols].median())

    # 무한값 → 0
    features = features.replace([np.inf, -np.inf], np.nan).fillna(0)

    # 최근 days_back 일만 반환 (웜업 기간 제외)
    features = features.tail(days_back)
    logger.info(f"[Feature] {ticker} 완성: {features.shape[0]}행 × {features.shape[1]}컬럼")
    return features


def create_labels(close: pd.Series, horizon: int = 1) -> pd.Series:
    """
    이진 레이블 (다음 horizon일 후 상승=1, 하락=0)
    Look-ahead bias 없음: shift(-horizon)으로 미래값 참조
    """
    future_return = close.astype(float).pct_change(horizon).shift(-horizon)
    return (future_return > 0).astype(int)
