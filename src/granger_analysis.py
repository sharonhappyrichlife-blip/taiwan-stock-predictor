import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import grangercausalitytests, adfuller
from statsmodels.tsa.vector_ar.var_model import VAR
import warnings
warnings.filterwarnings("ignore")


def check_stationarity(series: pd.Series, name: str = "") -> dict:
    """ADF stationarity test."""
    clean = series.dropna()
    result = adfuller(clean, autolag="AIC")
    return {
        "name": name,
        "adf_stat": result[0],
        "p_value": result[1],
        "is_stationary": result[1] < 0.05,
        "critical_values": result[4],
    }


def make_stationary(series: pd.Series) -> pd.Series:
    """Difference series until stationary."""
    s = series.dropna()
    result = adfuller(s, autolag="AIC")
    if result[1] < 0.05:
        return s
    return s.diff().dropna()


def run_granger_causality(
    cause: pd.Series,
    effect: pd.Series,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict:
    """
    Test whether `cause` Granger-causes `effect`.
    Returns test results for lags 1..max_lag.
    """
    cause_s = make_stationary(cause)
    effect_s = make_stationary(effect)

    # Align on common dates
    combined = pd.concat([effect_s, cause_s], axis=1).dropna()
    combined.columns = ["effect", "cause"]

    try:
        results = grangercausalitytests(combined[["effect", "cause"]], maxlag=max_lag, verbose=False)
    except Exception as e:
        return {"error": str(e), "results": {}}

    parsed = {}
    for lag, tests in results.items():
        ssr_ftest = tests[0]["ssr_ftest"]
        parsed[lag] = {
            "f_stat": ssr_ftest[0],
            "p_value": ssr_ftest[1],
            "df_denom": ssr_ftest[3],
            "significant": ssr_ftest[1] < significance,
        }

    best_lag = min(parsed, key=lambda k: parsed[k]["p_value"])
    return {
        "results": parsed,
        "best_lag": best_lag,
        "best_p_value": parsed[best_lag]["p_value"],
        "granger_causes": parsed[best_lag]["p_value"] < significance,
    }


def sentiment_stock_granger(
    sentiment_series: pd.Series,
    stock_returns: pd.Series,
    max_lag: int = 5,
) -> dict:
    """
    Comprehensive Granger test: does sentiment Granger-cause returns,
    and does returns Granger-cause sentiment?
    """
    sentiment_to_return = run_granger_causality(sentiment_series, stock_returns, max_lag)
    return_to_sentiment = run_granger_causality(stock_returns, sentiment_series, max_lag)

    return {
        "sentiment_causes_return": sentiment_to_return,
        "return_causes_sentiment": return_to_sentiment,
        "stationarity": {
            "sentiment": check_stationarity(sentiment_series, "sentiment"),
            "returns": check_stationarity(stock_returns, "returns"),
        },
    }


def var_model_fit(data: pd.DataFrame, max_lag: int = 5) -> dict:
    """Fit VAR model and return lag order selection."""
    clean = data.dropna()
    # Make all series stationary
    stationary_data = pd.DataFrame({col: make_stationary(clean[col]) for col in clean.columns}).dropna()

    try:
        model = VAR(stationary_data)
        lag_order = model.select_order(maxlags=max_lag)
        best_lag = lag_order.aic
        fitted = model.fit(best_lag)
        return {
            "aic_lag": best_lag,
            "bic_lag": lag_order.bic,
            "summary": str(fitted.summary()),
            "irf_periods": 10,
        }
    except Exception as e:
        return {"error": str(e)}


def cross_correlation_analysis(series1: pd.Series, series2: pd.Series, max_lag: int = 10) -> pd.DataFrame:
    """Compute cross-correlation at multiple lags."""
    s1 = (series1 - series1.mean()) / series1.std()
    s2 = (series2 - series2.mean()) / series2.std()
    combined = pd.concat([s1, s2], axis=1).dropna()
    s1_clean = combined.iloc[:, 0]
    s2_clean = combined.iloc[:, 1]

    lags = range(-max_lag, max_lag + 1)
    corrs = []
    for lag in lags:
        if lag < 0:
            corr = s1_clean.iloc[:lag].corr(s2_clean.iloc[-lag:])
        elif lag > 0:
            corr = s1_clean.iloc[lag:].corr(s2_clean.iloc[:-lag])
        else:
            corr = s1_clean.corr(s2_clean)
        corrs.append({"lag": lag, "correlation": corr})
    return pd.DataFrame(corrs)
