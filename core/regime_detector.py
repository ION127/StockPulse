"""
시장 국면(Regime) 감지 모듈

주식 시장은 강세/횡보/약세 국면에 따라 같은 기술적 지표의 의미가 다름.
국면을 피처로 추가하면 모델이 환경별로 다르게 반응 가능.

국면 정의:
    0 = 약세장 (Bear)  : 하락 추세 + 고변동성
    1 = 횡보장 (Neutral): 방향성 없음 + 중간 변동성
    2 = 강세장 (Bull)  : 상승 추세 + 저변동성
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def detect_regime_rule_based(
    price_series: pd.Series,
    fast_window: int = 20,
    slow_window: int = 60,
    vol_window: int = 20,
) -> pd.Series:
    """
    규칙 기반 시장 국면 감지 (빠르고 안정적)

    로직:
    - 이동평균 정배열(fast > slow) AND 저변동성 → 강세(2)
    - 이동평균 역배열(fast < slow) AND 고변동성 → 약세(0)
    - 그 외 → 횡보(1)

    Args:
        price_series: 종가 Series (날짜 인덱스)

    Returns:
        Series[int] (0=약세, 1=횡보, 2=강세)
    """
    price = price_series.astype(float)

    fast_ma = price.rolling(fast_window, min_periods=fast_window // 2).mean()
    slow_ma = price.rolling(slow_window, min_periods=slow_window // 2).mean()

    # 변동성: 20일 일간 수익률 표준편차
    daily_ret = price.pct_change()
    vol = daily_ret.rolling(vol_window, min_periods=vol_window // 2).std()
    vol_median = vol.rolling(120, min_periods=20).median()

    # 추세 방향
    trend_up   = fast_ma > slow_ma
    trend_down = fast_ma < slow_ma

    # 변동성 수준
    high_vol = vol > vol_median * 1.2
    low_vol  = vol < vol_median * 0.8

    regime = pd.Series(1, index=price.index, dtype=int)  # 기본: 횡보
    regime[trend_up   & ~high_vol] = 2   # 강세
    regime[trend_down & high_vol]  = 0   # 약세

    return regime


def detect_regime_hmm(price_series: pd.Series, n_states: int = 3) -> pd.Series:
    """
    HMM(Hidden Markov Model) 기반 국면 감지 (더 정교함)
    hmmlearn 설치 필요: pip install hmmlearn

    Args:
        price_series: 종가 Series
        n_states: 국면 수 (기본 3: 약세/횡보/강세)

    Returns:
        Series[int] — 상태 번호 (수익률 순으로 재정렬됨)
    """
    try:
        from hmmlearn.hmm import GaussianHMM

        daily_ret = price_series.pct_change().dropna().values.reshape(-1, 1)
        if len(daily_ret) < 60:
            logger.warning("[Regime] HMM 학습 데이터 부족 → 규칙 기반으로 fallback")
            return detect_regime_rule_based(price_series)

        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            random_state=42,
        )
        model.fit(daily_ret)
        hidden_states = model.predict(daily_ret)

        # 상태를 수익률 평균 기준으로 재정렬 (0=최저, 2=최고)
        state_means = [daily_ret[hidden_states == s].mean() for s in range(n_states)]
        rank_map = {s: rank for rank, s in enumerate(np.argsort(state_means))}
        remapped = np.array([rank_map[s] for s in hidden_states])

        # 인덱스 복원 (dropna 때문에 첫 행 제거됨)
        result = pd.Series(1, index=price_series.index, dtype=int)
        result.iloc[1:] = remapped
        return result

    except ImportError:
        logger.debug("[Regime] hmmlearn 미설치 → 규칙 기반으로 fallback")
        return detect_regime_rule_based(price_series)
    except Exception as e:
        logger.warning(f"[Regime] HMM 실패 → 규칙 기반으로 fallback: {e}")
        return detect_regime_rule_based(price_series)


def add_regime_features(features: pd.DataFrame, use_hmm: bool = False) -> pd.DataFrame:
    """
    피처 DataFrame에 국면 관련 컬럼 추가

    추가 컬럼:
        regime          : 현재 국면 (0/1/2)
        regime_duration : 현재 국면 지속 일수
        regime_is_bull  : 강세장 여부 (0/1)
        regime_is_bear  : 약세장 여부 (0/1)
        regime_changed  : 국면 전환 여부 (0/1)
    """
    if "close" not in features.columns:
        return features

    df = features.copy()

    if use_hmm:
        regime = detect_regime_hmm(df["close"])
    else:
        regime = detect_regime_rule_based(df["close"])

    df["regime"] = regime.values

    # 국면 지속 일수
    duration = []
    count = 0
    prev = -1
    for r in df["regime"]:
        if r != prev:
            count = 1
            prev = r
        else:
            count += 1
        duration.append(count)
    df["regime_duration"] = duration

    # 이진 플래그
    df["regime_is_bull"] = (df["regime"] == 2).astype(int)
    df["regime_is_bear"] = (df["regime"] == 0).astype(int)

    # 국면 전환 감지
    df["regime_changed"] = (df["regime"].diff().abs() > 0).astype(int)

    return df


def get_kospi_regime(macro_df: pd.DataFrame, use_hmm: bool = False) -> Optional[pd.Series]:
    """
    KOSPI 기반 시장 전체 국면

    macro_df에 'kospi' 컬럼이 있어야 함
    """
    if macro_df is None or macro_df.empty or "kospi" not in macro_df.columns:
        return None

    kospi = macro_df["kospi"].dropna()
    if len(kospi) < 30:
        return None

    if use_hmm:
        return detect_regime_hmm(kospi)
    return detect_regime_rule_based(kospi)
