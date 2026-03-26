"""
주가 방향성 예측 ML 모델 v2
- 앙상블: LightGBM + XGBoost + CatBoost (Soft Voting)
- Optuna 하이퍼파라미터 자동 튜닝
- Walk-forward 검증 (실전 시뮬레이션)
- SHAP 피처 중요도 (LightGBM 기반)
- 자동 재학습 트리거
"""

import logging
import os
from datetime import datetime
from typing import Optional

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = os.getenv("MODEL_DIR", "/app/models")
RETRAIN_ACCURACY_THRESHOLD = float(os.getenv("ML_RETRAIN_THRESHOLD", "0.52"))
RETRAIN_MAX_DAYS = int(os.getenv("ML_RETRAIN_MAX_DAYS", "7"))

# 앙상블 가중치 (성능 테스트 후 조정 가능)
ENSEMBLE_WEIGHTS = {
    "lgb": 0.4,
    "xgb": 0.35,
    "cat": 0.25,
}

# 피처 그룹 (존재하는 컬럼만 실제로 사용됨)
FEATURE_GROUPS = {
    "technical": [
        "rsi_14", "macd", "macd_signal", "macd_hist",
        "bb_position", "bb_width",
        "price_sma5_ratio", "price_sma20_ratio", "price_sma60_ratio",
        "atr_ratio", "vol_ratio", "vol_surge", "obv_ratio",
        "ret_3d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
        "vol_5d", "vol_20d", "vol_ratio_5_20", "pos_52w",
        "stoch_k", "stoch_d", "cci_20",
        "gap_pct", "candle_body", "upper_shadow", "lower_shadow", "bullish_candle",
    ],
    "supply": [
        "foreign_net", "institution_net", "individual_net",
        "foreign_net_3d", "foreign_net_5d", "foreign_net_momentum",
        "institution_net_3d", "institution_net_5d", "institution_net_momentum",
        "short_balance_ratio",
        "mkt_foreign_net", "mkt_institution_net",
        "credit_balance_ratio", "credit_balance_chg5", "credit_balance_chg20",
        "program_net",
        # 대차잔고 (공매도 선행 1~2주)
        "lending_balance", "lending_balance_ratio", "lending_chg5", "lending_chg20",
    ],
    "macro": [
        "vix", "vix_change_5d", "usd_krw", "oil_price",
        "kospi", "kospi_return_5d", "kospi_return_20d",
        "nasdaq", "gold_price", "us_10y_yield", "us_3m_yield",
        "yield_curve", "dxy", "kosdaq",
        "fear_greed", "is_fomc_month", "is_quarter_end",
        "kospi_regime",
        # VKOSPI (한국판 VIX)
        "vkospi", "vkospi_chg5",
        # BOK 기준금리 시계열 (API 키 있을 때만)
        "bok_base_rate", "bok_rate_chg",
        # 투자자예탁금 (시장 유동성 선행 1~2주)
        "investor_deposit", "deposit_chg5", "deposit_chg20",
    ],
    "regime": [
        "regime", "regime_duration", "regime_is_bull",
        "regime_is_bear", "regime_changed",
    ],
    "disclosure": [
        "disclosure_sentiment", "has_capital_increase", "has_buyback",
        "has_bond", "disclosure_count",
        "disclosure_sentiment_7d", "disclosure_sentiment_30d",
    ],
    "fundamental": [
        "fin_debt_ratio", "fin_roe", "fin_operating_margin",
        "fin_net_margin", "fin_current_ratio", "fin_eps", "fin_bps",
    ],
}

ALL_FEATURES = [f for group in FEATURE_GROUPS.values() for f in group]


# ── 유틸리티 ─────────────────────────────────────────────────────────────

def _model_paths(ticker: str) -> tuple[str, str, str, str]:
    """(lgb_path, xgb_path, cat_path, meta_path)"""
    safe = ticker.replace(":", "_").replace(".", "_")
    base = os.path.join(MODEL_DIR, safe)
    return f"{base}_lgb.pkl", f"{base}_xgb.pkl", f"{base}_cat.pkl", f"{base}_meta.pkl"


def _prepare_X(features_df: pd.DataFrame, feature_list: list[str]) -> pd.DataFrame:
    avail = [c for c in feature_list if c in features_df.columns]
    X = features_df[avail].copy()
    X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median())
    return X


# ── Optuna 튜닝 ───────────────────────────────────────────────────────────

def _tune_lgb(X: pd.DataFrame, y: pd.Series, n_trials: int = 30) -> dict:
    """LightGBM 하이퍼파라미터 Optuna 튜닝"""
    try:
        import optuna
        import lightgbm as lgb
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.metrics import roc_auc_score

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            params = {
                "objective":         "binary",
                "metric":            "auc",
                "verbose":           -1,
                "num_leaves":        trial.suggest_int("num_leaves", 15, 63),
                "max_depth":         trial.suggest_int("max_depth", 3, 8),
                "learning_rate":     trial.suggest_float("lr", 0.01, 0.1, log=True),
                "feature_fraction":  trial.suggest_float("ff", 0.5, 1.0),
                "bagging_fraction":  trial.suggest_float("bf", 0.5, 1.0),
                "bagging_freq":      5,
                "min_child_samples": trial.suggest_int("mcs", 10, 50),
                "lambda_l1":         trial.suggest_float("l1", 1e-4, 10.0, log=True),
                "lambda_l2":         trial.suggest_float("l2", 1e-4, 10.0, log=True),
                "random_state":      42,
            }
            tscv = TimeSeriesSplit(n_splits=3)
            scores = []
            for tr_idx, val_idx in tscv.split(X):
                m = lgb.LGBMClassifier(**params, n_estimators=200)
                m.fit(X.iloc[tr_idx], y.iloc[tr_idx],
                      callbacks=[lgb.log_evaluation(period=-1)])
                prob = m.predict_proba(X.iloc[val_idx])[:, 1]
                try:
                    scores.append(roc_auc_score(y.iloc[val_idx], prob))
                except Exception:
                    scores.append(0.5)
            return np.mean(scores)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, timeout=180)
        return study.best_params
    except Exception as e:
        logger.warning(f"[Optuna] LGB 튜닝 실패, 기본값 사용: {e}")
        return {}


def _tune_xgb(X: pd.DataFrame, y: pd.Series, n_trials: int = 20) -> dict:
    """XGBoost 하이퍼파라미터 Optuna 튜닝"""
    try:
        import optuna
        from xgboost import XGBClassifier
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.metrics import roc_auc_score

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            params = {
                "n_estimators":    200,
                "max_depth":       trial.suggest_int("max_depth", 3, 7),
                "learning_rate":   trial.suggest_float("lr", 0.01, 0.1, log=True),
                "subsample":       trial.suggest_float("sub", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("col", 0.5, 1.0),
                "reg_alpha":       trial.suggest_float("ra", 1e-4, 10.0, log=True),
                "reg_lambda":      trial.suggest_float("rl", 1e-4, 10.0, log=True),
                "use_label_encoder": False,
                "eval_metric":     "logloss",
                "verbosity":       0,
                "random_state":    42,
            }
            tscv = TimeSeriesSplit(n_splits=3)
            scores = []
            for tr_idx, val_idx in tscv.split(X):
                m = XGBClassifier(**params)
                m.fit(X.iloc[tr_idx], y.iloc[tr_idx], verbose=False)
                prob = m.predict_proba(X.iloc[val_idx])[:, 1]
                try:
                    scores.append(roc_auc_score(y.iloc[val_idx], prob))
                except Exception:
                    scores.append(0.5)
            return np.mean(scores)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, timeout=120)
        return study.best_params
    except Exception as e:
        logger.warning(f"[Optuna] XGB 튜닝 실패, 기본값 사용: {e}")
        return {}


# ── 학습 ─────────────────────────────────────────────────────────────────

def train(
    ticker: str,
    features_df: pd.DataFrame,
    labels: pd.Series,
    use_optuna: bool = False,
) -> dict:
    """
    LightGBM + XGBoost + CatBoost 앙상블 학습

    Args:
        ticker       : 종목코드
        features_df  : 피처 DataFrame
        labels       : 레이블 Series (0/1)
        use_optuna   : Optuna 튜닝 사용 여부 (주간 재학습 시 권장)

    Returns:
        dict(cv_accuracy, cv_auc, feature_importance, train_date, n_samples)
    """
    import lightgbm as lgb
    from xgboost import XGBClassifier
    from catboost import CatBoostClassifier
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.model_selection import TimeSeriesSplit

    avail_feats = [c for c in ALL_FEATURES if c in features_df.columns]
    if not avail_feats:
        avail_feats = list(features_df.select_dtypes(include=[np.number]).columns)

    X = _prepare_X(features_df, avail_feats)
    y = labels.loc[X.index].dropna()
    X = X.loc[y.index]

    if len(X) < 60:
        raise ValueError(f"학습 데이터 부족: {len(X)}행")

    logger.info(f"[ML] {ticker} 앙상블 학습 시작 | {len(X)}행 × {len(avail_feats)}피처")

    # ── Optuna 튜닝 (선택) ────────────────────────────────────────────────
    lgb_extra, xgb_extra = {}, {}
    if use_optuna:
        logger.info(f"[ML] {ticker} Optuna 튜닝 중...")
        lgb_extra = _tune_lgb(X, y, n_trials=30)
        xgb_extra = _tune_xgb(X, y, n_trials=20)

    # ── 기본 파라미터 ─────────────────────────────────────────────────────
    lgb_params = {
        "objective": "binary", "metric": ["binary_logloss", "auc"],
        "num_leaves": 31, "max_depth": 6, "learning_rate": 0.05,
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 5,
        "min_child_samples": 20, "lambda_l1": 0.1, "lambda_l2": 0.1,
        "verbose": -1, "random_state": 42,
        **lgb_extra,
    }
    xgb_params = {
        "n_estimators": 300, "max_depth": 5, "learning_rate": 0.05,
        "subsample": 0.8, "colsample_bytree": 0.8,
        "reg_alpha": 0.1, "reg_lambda": 0.1,
        "use_label_encoder": False, "eval_metric": "logloss",
        "verbosity": 0, "random_state": 42,
        **xgb_extra,
    }
    cat_params = {
        "iterations": 300, "depth": 6, "learning_rate": 0.05,
        "l2_leaf_reg": 3.0, "random_seed": 42,
        "verbose": 0,
    }

    # ── TimeSeriesSplit 교차 검증 ─────────────────────────────────────────
    tscv = TimeSeriesSplit(n_splits=5)
    acc_scores, auc_scores = [], []

    for tr_idx, val_idx in tscv.split(X):
        X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[tr_idx], y.iloc[val_idx]

        # LGB
        m_lgb = lgb.LGBMClassifier(**lgb_params, n_estimators=300)
        m_lgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  callbacks=[lgb.early_stopping(30, verbose=False),
                              lgb.log_evaluation(-1)])
        p_lgb = m_lgb.predict_proba(X_val)[:, 1]

        # XGB
        m_xgb = XGBClassifier(**xgb_params, early_stopping_rounds=30)
        m_xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        p_xgb = m_xgb.predict_proba(X_val)[:, 1]

        # CatBoost
        m_cat = CatBoostClassifier(**cat_params)
        m_cat.fit(X_tr, y_tr, eval_set=(X_val, y_val),
                  early_stopping_rounds=30, verbose=False)
        p_cat = m_cat.predict_proba(X_val)[:, 1]

        # 앙상블 (가중 평균)
        p_ens = (ENSEMBLE_WEIGHTS["lgb"] * p_lgb
                 + ENSEMBLE_WEIGHTS["xgb"] * p_xgb
                 + ENSEMBLE_WEIGHTS["cat"] * p_cat)

        preds = (p_ens > 0.5).astype(int)
        acc_scores.append(accuracy_score(y_val, preds))
        try:
            auc_scores.append(roc_auc_score(y_val, p_ens))
        except Exception:
            pass

    cv_acc = float(np.mean(acc_scores))
    cv_auc = float(np.mean(auc_scores)) if auc_scores else 0.0
    logger.info(f"[ML] {ticker} CV → Acc={cv_acc:.4f} AUC={cv_auc:.4f} (±{np.std(acc_scores):.4f})")

    # ── 전체 데이터로 최종 모델 학습 ─────────────────────────────────────
    final_lgb = lgb.LGBMClassifier(**{**lgb_params, "n_estimators": 500})
    final_lgb.fit(X, y, callbacks=[lgb.log_evaluation(-1)])

    final_xgb = XGBClassifier(**{**xgb_params, "n_estimators": 500})
    final_xgb.fit(X, y, verbose=False)

    final_cat = CatBoostClassifier(**{**cat_params, "iterations": 500})
    final_cat.fit(X, y, verbose=False)

    # 피처 중요도 (LGB gain 기준)
    importance = dict(sorted(
        zip(avail_feats, final_lgb.feature_importances_),
        key=lambda x: x[1], reverse=True,
    ))

    # ── 저장 ─────────────────────────────────────────────────────────────
    os.makedirs(MODEL_DIR, exist_ok=True)
    lgb_path, xgb_path, cat_path, meta_path = _model_paths(ticker)
    joblib.dump(final_lgb, lgb_path)
    joblib.dump(final_xgb, xgb_path)
    joblib.dump(final_cat, cat_path)

    meta = {
        "ticker":      ticker,
        "features":    avail_feats,
        "cv_accuracy": cv_acc,
        "cv_auc":      cv_auc,
        "train_date":  datetime.now().isoformat(),
        "n_samples":   len(X),
        "importance":  importance,
        "used_optuna": use_optuna,
    }
    joblib.dump(meta, meta_path)
    logger.info(f"[ML] {ticker} 저장 완료")

    return {
        "cv_accuracy":        cv_acc,
        "cv_auc":             cv_auc,
        "feature_importance": importance,
        "train_date":         meta["train_date"],
        "n_samples":          len(X),
    }


# ── 예측 ─────────────────────────────────────────────────────────────────

def predict(ticker: str, features_df: pd.DataFrame) -> Optional[dict]:
    """
    앙상블 예측 (LGB + XGB + CatBoost 가중 평균)

    Returns:
        dict(ticker, direction, up_prob, confidence, shap_top5,
             cv_accuracy, cv_auc, model_train_date)
    """
    lgb_path, xgb_path, cat_path, meta_path = _model_paths(ticker)
    if not os.path.exists(meta_path):
        logger.warning(f"[ML] 모델 없음: {ticker}")
        return None

    try:
        meta     = joblib.load(meta_path)
        avail    = meta["features"]
        X        = _prepare_X(features_df, avail).iloc[[-1]]

        probs = []

        # LGB
        if os.path.exists(lgb_path):
            p = joblib.load(lgb_path).predict_proba(X)[0][1]
            probs.append(("lgb", p))

        # XGB
        if os.path.exists(xgb_path):
            p = joblib.load(xgb_path).predict_proba(X)[0][1]
            probs.append(("xgb", p))

        # CatBoost
        if os.path.exists(cat_path):
            p = joblib.load(cat_path).predict_proba(X)[0][1]
            probs.append(("cat", p))

        if not probs:
            return None

        # 가중 평균
        total_w = sum(ENSEMBLE_WEIGHTS.get(name, 1.0) for name, _ in probs)
        up_prob = sum(ENSEMBLE_WEIGHTS.get(name, 1.0) * p for name, p in probs) / total_w

        direction  = "상승" if up_prob > 0.5 else "하락"
        confidence = round(abs(up_prob - 0.5) * 200, 1)

        # SHAP (LGB 기반)
        shap_top5: dict = {}
        try:
            import shap
            lgb_model = joblib.load(lgb_path)
            explainer = shap.TreeExplainer(lgb_model)
            sv = explainer.shap_values(X)
            if isinstance(sv, list):
                sv = sv[1]
            top_idx = np.argsort(np.abs(sv[0]))[::-1][:5]
            shap_top5 = {avail[i]: round(float(sv[0][i]), 4) for i in top_idx}
        except Exception:
            pass

        return {
            "ticker":           ticker,
            "direction":        direction,
            "up_prob":          round(float(up_prob) * 100, 1),
            "confidence":       confidence,
            "shap_top5":        shap_top5,
            "model_probs":      {name: round(p * 100, 1) for name, p in probs},
            "cv_accuracy":      meta.get("cv_accuracy"),
            "cv_auc":           meta.get("cv_auc"),
            "model_train_date": meta.get("train_date"),
            "predicted_at":     datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"[ML] 예측 실패 ({ticker}): {e}")
        return None


# ── Walk-forward 검증 ────────────────────────────────────────────────────

def walk_forward_validation(
    features_df: pd.DataFrame,
    labels: pd.Series,
    train_window: int = 252,
    test_window: int = 21,
) -> dict:
    """
    Walk-forward 검증 (실전 시뮬레이션)
    매 test_window 거래일마다 재학습하는 방식으로 성능 평가

    Args:
        train_window : 학습 기간 (거래일, 기본 252일 = 1년)
        test_window  : 검증 기간 (거래일, 기본 21일 = 1개월)

    Returns:
        dict(wf_accuracy, wf_auc, period_accuracies, n_periods)
    """
    import lightgbm as lgb
    from sklearn.metrics import accuracy_score, roc_auc_score

    avail_feats = [c for c in ALL_FEATURES if c in features_df.columns]
    if not avail_feats:
        avail_feats = list(features_df.select_dtypes(include=[np.number]).columns)

    X = _prepare_X(features_df, avail_feats)
    y = labels.loc[X.index].dropna()
    X = X.loc[y.index]

    if len(X) < train_window + test_window:
        return {"wf_accuracy": 0.0, "n_periods": 0, "error": "데이터 부족"}

    params = {
        "objective": "binary", "metric": "auc",
        "num_leaves": 31, "learning_rate": 0.05,
        "feature_fraction": 0.8, "verbose": -1, "random_state": 42,
    }

    period_accs, period_aucs = [], []

    for i in range(train_window, len(X) - test_window + 1, test_window):
        X_tr = X.iloc[i - train_window:i]
        y_tr = y.iloc[i - train_window:i]
        X_te = X.iloc[i:i + test_window]
        y_te = y.iloc[i:i + test_window]

        m = lgb.LGBMClassifier(**params, n_estimators=200)
        m.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(-1)])

        preds = m.predict(X_te)
        proba = m.predict_proba(X_te)[:, 1]

        period_accs.append(accuracy_score(y_te, preds))
        try:
            period_aucs.append(roc_auc_score(y_te, proba))
        except Exception:
            pass

    if not period_accs:
        return {"wf_accuracy": 0.0, "n_periods": 0}

    result = {
        "wf_accuracy":       round(float(np.mean(period_accs)), 4),
        "wf_auc":            round(float(np.mean(period_aucs)), 4) if period_aucs else 0.0,
        "wf_std":            round(float(np.std(period_accs)), 4),
        "n_periods":         len(period_accs),
        "period_accuracies": [round(a, 4) for a in period_accs],
        "best_period_acc":   round(max(period_accs), 4),
        "worst_period_acc":  round(min(period_accs), 4),
    }
    logger.info(
        f"[WF] Walk-forward 완료: acc={result['wf_accuracy']:.4f} "
        f"auc={result['wf_auc']:.4f} ({result['n_periods']} periods)"
    )
    return result


# ── 유틸리티 ─────────────────────────────────────────────────────────────

def model_exists(ticker: str) -> bool:
    _, _, _, meta_path = _model_paths(ticker)
    return os.path.exists(meta_path)


def get_model_meta(ticker: str) -> Optional[dict]:
    _, _, _, meta_path = _model_paths(ticker)
    if not os.path.exists(meta_path):
        return None
    try:
        return joblib.load(meta_path)
    except Exception:
        return None


def should_retrain(ticker: str, recent_accuracy: float) -> bool:
    if recent_accuracy < RETRAIN_ACCURACY_THRESHOLD:
        logger.info(f"[ML] {ticker} 재학습 트리거 (acc {recent_accuracy:.4f} < {RETRAIN_ACCURACY_THRESHOLD})")
        return True
    meta = get_model_meta(ticker)
    if meta:
        age = (datetime.now() - datetime.fromisoformat(meta["train_date"])).days
        if age > RETRAIN_MAX_DAYS:
            logger.info(f"[ML] {ticker} 재학습 트리거 (모델 {age}일 경과)")
            return True
    return False


def evaluate_predictions(predictions: list[dict], actuals: list[dict]) -> dict:
    """예측 결과 vs 실제 결과 정확도 계산"""
    if not predictions or not actuals:
        return {"accuracy": 0.0, "sample_count": 0}

    actual_map = {(a["ticker"], a["date"]): a["actual_direction"] for a in actuals}
    y_pred, y_true = [], []

    for p in predictions:
        key = (p["ticker"], p.get("date", p.get("predicted_at", ""))[:10])
        if key in actual_map:
            y_pred.append(1 if p["direction"] == "상승" else 0)
            y_true.append(1 if actual_map[key] == "상승" else 0)

    if not y_pred:
        return {"accuracy": 0.0, "sample_count": 0}

    from sklearn.metrics import accuracy_score
    return {
        "accuracy":     round(accuracy_score(y_true, y_pred), 4),
        "sample_count": len(y_pred),
        "correct_up":   sum(1 for p, a in zip(y_pred, y_true) if p == 1 and a == 1),
        "correct_down": sum(1 for p, a in zip(y_pred, y_true) if p == 0 and a == 0),
    }
