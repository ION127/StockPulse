"""
KRX 수급 데이터 수집
- 외국인 / 기관 / 개인 순매수
- 공매도 잔고
- pykrx 라이브러리 (무료, API 키 불필요)
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


def _clean_ticker(ticker: str) -> str:
    return ticker.replace("KR:", "").replace(".KS", "").replace(".KQ", "")


def get_investor_trading(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    외국인 / 기관 / 개인 순매수 수량 (일별)

    Args:
        ticker: 종목코드 (KR:005930 or 005930)
        start_date / end_date: "YYYYMMDD"

    Returns columns: date, foreign_net, institution_net, individual_net
    """
    try:
        from pykrx import stock as krx

        code = _clean_ticker(ticker)
        df = krx.get_market_trading_volume_by_date(start_date, end_date, code)
        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {
            "외국인합계": "foreign_net",
            "외국인":     "foreign_net",
            "기관합계":   "institution_net",
            "개인":       "individual_net",
        }
        rename = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=rename)

        keep = [c for c in ["foreign_net", "institution_net", "individual_net"] if c in df.columns]
        result = df[keep].copy()
        result.index = pd.to_datetime(df.index)
        result.index.name = "date"
        return result

    except Exception as e:
        logger.warning(f"[KRX] 수급 수집 실패 ({ticker}): {e}")
        return pd.DataFrame()


def get_short_selling(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    공매도 잔고 비율 (일별)

    Returns columns: date, short_balance, short_balance_ratio
    """
    try:
        from pykrx import stock as krx

        code = _clean_ticker(ticker)
        df = krx.get_shorting_balance_by_date(start_date, end_date, code)
        if df is None or df.empty:
            return pd.DataFrame()

        result = pd.DataFrame(index=pd.to_datetime(df.index))
        result.index.name = "date"
        if len(df.columns) >= 1:
            result["short_balance"] = df.iloc[:, 0].values
        if len(df.columns) >= 2:
            result["short_balance_ratio"] = df.iloc[:, 1].values
        return result

    except Exception as e:
        logger.warning(f"[KRX] 공매도 수집 실패 ({ticker}): {e}")
        return pd.DataFrame()


def get_market_trading(start_date: str, end_date: str) -> pd.DataFrame:
    """
    KOSPI 시장 전체 수급 (외국인/기관 합산)

    Returns columns: date, mkt_foreign_net, mkt_institution_net
    """
    try:
        from pykrx import stock as krx

        df = krx.get_market_trading_volume_by_date(start_date, end_date, "KOSPI")
        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {
            "외국인합계": "mkt_foreign_net",
            "외국인":     "mkt_foreign_net",
            "기관합계":   "mkt_institution_net",
        }
        rename = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=rename)

        keep = [c for c in ["mkt_foreign_net", "mkt_institution_net"] if c in df.columns]
        result = df[keep].copy()
        result.index = pd.to_datetime(df.index)
        result.index.name = "date"
        return result

    except Exception as e:
        logger.warning(f"[KRX] 시장 수급 수집 실패: {e}")
        return pd.DataFrame()


def get_credit_balance(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    신용잔고 / 대주잔고 (일별)
    - 신용잔고 급증: 개인 레버리지 과열 → 역추세 하락 신호
    - 신용잔고 급감: 반대매매 발생 가능 → 추가 하락 신호

    Returns columns: credit_balance, credit_balance_ratio
    """
    try:
        from pykrx import stock as krx

        code = _clean_ticker(ticker)
        df = krx.get_market_cap_by_date(start_date, end_date, code)
        if df is None or df.empty:
            return pd.DataFrame()

        # pykrx credit balance API
        credit_df = krx.get_shorting_investor_by_date(start_date, end_date, code)
        if credit_df is None or credit_df.empty:
            return pd.DataFrame()

        result = pd.DataFrame(index=pd.to_datetime(credit_df.index))
        result.index.name = "date"
        if len(credit_df.columns) >= 1:
            result["credit_balance"] = credit_df.iloc[:, 0].values
        if len(credit_df.columns) >= 2:
            result["credit_balance_ratio"] = credit_df.iloc[:, 1].values

        # 5일/20일 변화율 추가
        if "credit_balance" in result.columns:
            result["credit_balance_chg5"]  = result["credit_balance"].pct_change(5)
            result["credit_balance_chg20"] = result["credit_balance"].pct_change(20)

        return result

    except Exception as e:
        logger.warning(f"[KRX] 신용잔고 수집 실패 ({ticker}): {e}")
        return pd.DataFrame()


def get_program_trading(start_date: str, end_date: str) -> pd.DataFrame:
    """
    KOSPI 프로그램 매매 동향 (차익/비차익)
    - 프로그램 순매수 급증: 지수 추종 자금 유입 → 단기 상승 모멘텀

    Returns columns: program_buy, program_sell, program_net
    """
    try:
        from pykrx import stock as krx

        df = krx.get_market_trading_value_by_date(start_date, end_date, "KOSPI")
        if df is None or df.empty:
            return pd.DataFrame()

        result = pd.DataFrame(index=pd.to_datetime(df.index))
        result.index.name = "date"

        col_map = {
            "프로그램매수": "program_buy",
            "프로그램매도": "program_sell",
        }
        for src, dst in col_map.items():
            if src in df.columns:
                result[dst] = df[src].values

        if "program_buy" in result.columns and "program_sell" in result.columns:
            result["program_net"] = result["program_buy"] - result["program_sell"]

        return result

    except Exception as e:
        logger.warning(f"[KRX] 프로그램 매매 수집 실패: {e}")
        return pd.DataFrame()


def get_vkospi(start_date: str, end_date: str) -> pd.DataFrame:
    """
    VKOSPI (한국판 VIX) 일별 종가

    미국 VIX보다 한국 시장에 직접적인 공포/변동성 지수.
    KOSPI200 옵션의 내재변동성으로 산출 (KRX 공식 지수).

    Returns columns: vkospi
    """
    try:
        from pykrx import stock as krx

        # VKOSPI 지수 코드를 동적으로 탐색
        vkospi_code = None
        try:
            tickers = krx.get_index_ticker_list(market="KRX")
            for t in tickers:
                name = krx.get_index_ticker_name(t)
                if "VKOSPI" in str(name).upper():
                    vkospi_code = t
                    break
        except Exception:
            pass

        # 동적 탐색 실패 시 알려진 코드 시도
        if not vkospi_code:
            for candidate in ["1003", "2203", "1510"]:
                try:
                    test = krx.get_index_ohlcv_by_date(start_date, end_date, candidate)
                    if test is not None and not test.empty:
                        vkospi_code = candidate
                        break
                except Exception:
                    continue

        if not vkospi_code:
            return pd.DataFrame()

        df = krx.get_index_ohlcv_by_date(start_date, end_date, vkospi_code)
        if df is None or df.empty:
            return pd.DataFrame()

        close_col = "종가" if "종가" in df.columns else df.columns[-1]
        result = pd.DataFrame(index=pd.to_datetime(df.index))
        result.index.name = "date"
        result["vkospi"] = df[close_col].values

        # 5일 변화율 (공포 급증 탐지)
        result["vkospi_chg5"] = result["vkospi"].pct_change(5)

        return result

    except Exception as e:
        logger.warning(f"[KRX] VKOSPI 수집 실패: {e}")
        return pd.DataFrame()


def get_lending_balance(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    대차잔고 (Stock Lending Balance) — 공매도 선행지표

    공매도 잔고(실제 체결)보다 1~2주 선행.
    대차잔고 급증 = 기관이 공매도 준비 중 → 하락 선행 신호.
    대차잔고 급감 = 숏 커버링 예정 → 단기 반등 신호.

    Returns columns: lending_balance, lending_balance_ratio,
                     lending_chg5, lending_chg20
    """
    try:
        from pykrx import stock as krx

        code = _clean_ticker(ticker)

        # pykrx: get_shorting_investor_by_date가 대차잔고를 포함하는 경우
        df = krx.get_shorting_investor_by_date(start_date, end_date, code)
        if df is None or df.empty:
            return pd.DataFrame()

        result = pd.DataFrame(index=pd.to_datetime(df.index))
        result.index.name = "date"

        # 컬럼명 탐색 (pykrx 버전별 다름)
        for col in df.columns:
            col_str = str(col)
            if "대차" in col_str or "잔고" in col_str:
                result["lending_balance"] = df[col].values
                break
        else:
            # 첫 번째 컬럼을 대차잔고로 간주
            if len(df.columns) >= 1:
                result["lending_balance"] = df.iloc[:, 0].values

        if "lending_balance" not in result.columns or result["lending_balance"].isna().all():
            return pd.DataFrame()

        # 비율 (전체 발행주식 대비) — 두 번째 컬럼이 비율인 경우
        if len(df.columns) >= 2:
            result["lending_balance_ratio"] = df.iloc[:, 1].values

        # 변화율 (핵심 신호: 추세 변화가 중요)
        result["lending_chg5"]  = result["lending_balance"].pct_change(5)
        result["lending_chg20"] = result["lending_balance"].pct_change(20)

        return result

    except Exception as e:
        logger.debug(f"[KRX] 대차잔고 수집 실패 ({ticker}): {e}")
        return pd.DataFrame()


def get_ohlcv(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    일봉 OHLCV 데이터

    Returns columns: date, open, high, low, close, volume
    """
    try:
        from pykrx import stock as krx

        code = _clean_ticker(ticker)
        df = krx.get_market_ohlcv_by_date(start_date, end_date, code)
        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        return df[keep]

    except Exception as e:
        logger.warning(f"[KRX] OHLCV 수집 실패 ({ticker}): {e}")
        return pd.DataFrame()
