import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import grangercausalitytests, adfuller, kpss
from statsmodels.tsa.vector_ar.var_model import VAR
from statsmodels.tsa.vector_ar.irf import IRAnalysis
from scipy import stats
import warnings
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# Stationarity helpers
# ─────────────────────────────────────────────────────────────────────────────

def check_stationarity(series: pd.Series, name: str = "") -> dict:
    """ADF + KPSS stationarity tests (confirmatory pair)."""
    clean = series.dropna()
    adf = adfuller(clean, autolag="AIC")
    try:
        kpss_stat, kpss_p, _, _ = kpss(clean, regression="c", nlags="auto")
        kpss_stationary = kpss_p > 0.05   # H0 of KPSS is stationary
    except Exception:
        kpss_stat, kpss_p, kpss_stationary = np.nan, np.nan, None

    adf_stationary = adf[1] < 0.05        # H0 of ADF is unit root
    # Both tests agree → confident; disagree → uncertain
    if adf_stationary and kpss_stationary:
        conclusion = "stationary"
    elif not adf_stationary and not kpss_stationary:
        conclusion = "non_stationary"
    else:
        conclusion = "uncertain"

    return {
        "name": name,
        "adf_stat": adf[0],
        "adf_p": adf[1],
        "kpss_stat": kpss_stat,
        "kpss_p": kpss_p,
        "is_stationary": adf_stationary,
        "conclusion": conclusion,
        "critical_values": adf[4],
        "n_diff": 0,
    }


def make_stationary(series: pd.Series, max_diff: int = 2) -> tuple[pd.Series, int]:
    """
    Difference series until ADF rejects unit root.
    Returns (stationary_series, n_diffs_applied).
    """
    s = series.dropna()
    for d in range(max_diff + 1):
        if adfuller(s, autolag="AIC")[1] < 0.05:
            return s, d
        s = s.diff().dropna()
    return s, max_diff


# ─────────────────────────────────────────────────────────────────────────────
# Core Granger test
# ─────────────────────────────────────────────────────────────────────────────

def run_granger_causality(
    cause: pd.Series,
    effect: pd.Series,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict:
    """
    Test whether `cause` Granger-causes `effect`.
    Returns per-lag F-test results plus best-lag summary.
    """
    cause_s, _ = make_stationary(cause)
    effect_s, _ = make_stationary(effect)

    combined = pd.concat([effect_s, cause_s], axis=1).dropna()
    combined.columns = ["effect", "cause"]

    if len(combined) < max_lag * 3 + 10:
        return {"error": f"不足夠的資料點 ({len(combined)})", "results": {}}

    try:
        raw = grangercausalitytests(combined[["effect", "cause"]], maxlag=max_lag, verbose=False)
    except Exception as e:
        return {"error": str(e), "results": {}}

    parsed = {}
    for lag, tests in raw.items():
        f = tests[0]["ssr_ftest"]
        parsed[lag] = {
            "f_stat": f[0],
            "p_value": f[1],
            "df_num": f[2],
            "df_denom": f[3],
            "significant": f[1] < significance,
        }

    best_lag = min(parsed, key=lambda k: parsed[k]["p_value"])
    return {
        "results": parsed,
        "best_lag": best_lag,
        "best_p_value": parsed[best_lag]["p_value"],
        "best_f_stat": parsed[best_lag]["f_stat"],
        "granger_causes": parsed[best_lag]["p_value"] < significance,
        "n_significant_lags": sum(v["significant"] for v in parsed.values()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lead / Lag analysis  ← NEW CORE MODULE
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_lead_lag_analysis(
    sentiment: pd.Series,
    price_returns: pd.Series,
    max_lag: int = 10,
    significance: float = 0.05,
) -> dict:
    """
    Systematic lead/lag analysis between sentiment and price returns.

    Positive lag  → sentiment LEADS price  (sentiment[t-k] predicts return[t])
    Negative lag  → sentiment LAGS price   (return[t-k] predicts sentiment[t])

    Returns
    -------
    dict with keys:
        lead_df        : DataFrame of lead results (sentiment predicts future return)
        lag_df         : DataFrame of lag results  (past return predicts sentiment)
        optimal_lead   : lag k where sentiment best predicts return
        optimal_lag    : lag k where return best predicts sentiment
        relationship   : 'sentiment_leads' | 'price_leads' | 'bidirectional' | 'none'
        summary        : human-readable dict
        cross_corr_df  : cross-correlation at each lead/lag
    """
    aligned = pd.concat([sentiment.rename("s"), price_returns.rename("r")], axis=1).dropna()
    s = aligned["s"]
    r = aligned["r"]

    # ── Cross-correlation (symmetric, no causality assumed) ──────────────────
    cc_rows = []
    for k in range(-max_lag, max_lag + 1):
        if k > 0:                          # sentiment k periods AHEAD of return
            corr, pval = stats.pearsonr(s.iloc[:-k], r.iloc[k:])
            label = f"情緒領先 {k} 期"
        elif k < 0:                        # sentiment k periods BEHIND return
            corr, pval = stats.pearsonr(s.iloc[-k:], r.iloc[:k])
            label = f"情緒落後 {abs(k)} 期"
        else:
            corr, pval = stats.pearsonr(s, r)
            label = "同期"
        cc_rows.append({
            "lag": k, "label": label,
            "correlation": corr, "p_value": pval,
            "significant": pval < significance,
        })
    cross_corr_df = pd.DataFrame(cc_rows)

    # ── Granger: sentiment[t-k] → return[t]  for k = 1..max_lag ────────────
    lead_rows = []
    for k in range(1, max_lag + 1):
        s_shifted = s.shift(k)
        data = pd.concat([r, s_shifted], axis=1).dropna()
        data.columns = ["effect", "cause"]
        if len(data) < 20:
            continue
        try:
            res = grangercausalitytests(data, maxlag=1, verbose=False)
            f = res[1][0]["ssr_ftest"]
            lead_rows.append({
                "lead_k": k,
                "f_stat": f[0],
                "p_value": f[1],
                "significant": f[1] < significance,
                "direction": "sentiment→return",
            })
        except Exception:
            pass
    lead_df = pd.DataFrame(lead_rows)

    # ── Granger: return[t-k] → sentiment[t]  for k = 1..max_lag ────────────
    lag_rows = []
    for k in range(1, max_lag + 1):
        r_shifted = r.shift(k)
        data = pd.concat([s, r_shifted], axis=1).dropna()
        data.columns = ["effect", "cause"]
        if len(data) < 20:
            continue
        try:
            res = grangercausalitytests(data, maxlag=1, verbose=False)
            f = res[1][0]["ssr_ftest"]
            lag_rows.append({
                "lag_k": k,
                "f_stat": f[0],
                "p_value": f[1],
                "significant": f[1] < significance,
                "direction": "return→sentiment",
            })
        except Exception:
            pass
    lag_df = pd.DataFrame(lag_rows)

    # ── Determine optimal lead/lag ───────────────────────────────────────────
    optimal_lead = (
        int(lead_df.loc[lead_df["p_value"].idxmin(), "lead_k"])
        if not lead_df.empty else None
    )
    optimal_lag = (
        int(lag_df.loc[lag_df["p_value"].idxmin(), "lag_k"])
        if not lag_df.empty else None
    )
    lead_sig = not lead_df.empty and lead_df["significant"].any()
    lag_sig = not lag_df.empty and lag_df["significant"].any()

    if lead_sig and lag_sig:
        relationship = "bidirectional"
    elif lead_sig:
        relationship = "sentiment_leads"
    elif lag_sig:
        relationship = "price_leads"
    else:
        relationship = "none"

    relationship_zh = {
        "sentiment_leads": "情緒領先股價",
        "price_leads": "股價領先情緒",
        "bidirectional": "雙向因果關係",
        "none": "無顯著因果關係",
    }[relationship]

    best_lead_p = float(lead_df["p_value"].min()) if not lead_df.empty else 1.0
    best_lag_p = float(lag_df["p_value"].min()) if not lag_df.empty else 1.0

    summary = {
        "relationship": relationship,
        "relationship_zh": relationship_zh,
        "optimal_lead_k": optimal_lead,
        "optimal_lag_k": optimal_lag,
        "best_lead_p_value": best_lead_p,
        "best_lag_p_value": best_lag_p,
        "n_significant_leads": int(lead_df["significant"].sum()) if not lead_df.empty else 0,
        "n_significant_lags": int(lag_df["significant"].sum()) if not lag_df.empty else 0,
        "interpretation": _interpret_lead_lag(relationship, optimal_lead, optimal_lag),
    }

    return {
        "lead_df": lead_df,
        "lag_df": lag_df,
        "cross_corr_df": cross_corr_df,
        "optimal_lead": optimal_lead,
        "optimal_lag": optimal_lag,
        "relationship": relationship,
        "summary": summary,
    }


def _interpret_lead_lag(relationship: str, lead_k: int | None, lag_k: int | None) -> str:
    if relationship == "sentiment_leads":
        return (
            f"情緒指標領先股價報酬約 {lead_k} 個交易日，"
            "可作為短期價格走勢的預測因子。"
        )
    elif relationship == "price_leads":
        return (
            f"股價報酬領先情緒變化約 {lag_k} 個交易日，"
            "情緒呈現對價格的後驗反應。"
        )
    elif relationship == "bidirectional":
        return (
            f"情緒與股價存在雙向因果：情緒領先 {lead_k} 日影響股價，"
            f"同時股價領先 {lag_k} 日回饋情緒，形成反饋迴路。"
        )
    return "在現有顯著水準下，情緒與股價報酬間未發現顯著的領先/落後關係。"


# ─────────────────────────────────────────────────────────────────────────────
# Rolling-window Granger (time-varying causality)
# ─────────────────────────────────────────────────────────────────────────────

def rolling_granger(
    cause: pd.Series,
    effect: pd.Series,
    window: int = 60,
    lag: int = 1,
    significance: float = 0.05,
) -> pd.DataFrame:
    """
    Rolling-window Granger causality to detect structural breaks.
    Returns DataFrame with columns: date, p_value, f_stat, significant.
    """
    cause_s, _ = make_stationary(cause)
    effect_s, _ = make_stationary(effect)
    combined = pd.concat([effect_s, cause_s], axis=1).dropna()
    combined.columns = ["effect", "cause"]

    rows = []
    for end in range(window, len(combined) + 1):
        window_data = combined.iloc[end - window: end]
        try:
            res = grangercausalitytests(window_data, maxlag=lag, verbose=False)
            f = res[lag][0]["ssr_ftest"]
            rows.append({
                "date": combined.index[end - 1],
                "p_value": f[1],
                "f_stat": f[0],
                "significant": f[1] < significance,
            })
        except Exception:
            rows.append({
                "date": combined.index[end - 1],
                "p_value": np.nan,
                "f_stat": np.nan,
                "significant": False,
            })
    return pd.DataFrame(rows).set_index("date")


# ─────────────────────────────────────────────────────────────────────────────
# VAR model + Impulse Response Function
# ─────────────────────────────────────────────────────────────────────────────

def var_model_fit(data: pd.DataFrame, max_lag: int = 5) -> dict:
    """Fit VAR model; return lag selection, fitted model, and IRF data."""
    clean = data.dropna()
    stat_cols = {}
    n_diffs = {}
    for col in clean.columns:
        s, d = make_stationary(clean[col])
        stat_cols[col] = s
        n_diffs[col] = d
    stationary_data = pd.DataFrame(stat_cols).dropna()

    try:
        model = VAR(stationary_data)
        lag_order = model.select_order(maxlags=max_lag)
        best_lag = max(lag_order.aic, 1)
        fitted = model.fit(best_lag)

        # Impulse Response Function
        irf: IRAnalysis = fitted.irf(periods=10)
        irf_data = {}
        for i, shock_col in enumerate(stationary_data.columns):
            for j, resp_col in enumerate(stationary_data.columns):
                key = f"{shock_col}→{resp_col}"
                irf_data[key] = {
                    "irfs": irf.irfs[:, j, i].tolist(),
                    "lower": irf.cum_effect_stderr(orth=False)[:, j, i].tolist()
                    if hasattr(irf, "cum_effect_stderr") else [],
                }

        return {
            "aic_lag": best_lag,
            "bic_lag": lag_order.bic,
            "hqic_lag": lag_order.hqic,
            "n_diffs": n_diffs,
            "irf_data": irf_data,
            "columns": list(stationary_data.columns),
            "n_obs": len(stationary_data),
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Predictive power score
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_predictive_score(
    sentiment: pd.Series,
    price_returns: pd.Series,
    lead_k: int = 1,
) -> dict:
    """
    Evaluate how well sentiment at t-lead_k predicts the direction of return at t.
    Uses sign-accuracy, Spearman rank correlation, and information coefficient (IC).
    """
    s = sentiment.shift(lead_k)
    aligned = pd.concat([s.rename("s"), price_returns.rename("r")], axis=1).dropna()

    if len(aligned) < 20:
        return {"error": "資料不足"}

    # Direction accuracy
    correct_direction = np.sign(aligned["s"]) == np.sign(aligned["r"])
    direction_accuracy = correct_direction.mean()

    # Spearman IC
    ic, ic_pval = stats.spearmanr(aligned["s"], aligned["r"])

    # Hit rate by quintile
    aligned["quintile"] = pd.qcut(aligned["s"], 5, labels=False, duplicates="drop")
    quintile_returns = aligned.groupby("quintile")["r"].mean()

    # Annualised IR (Information Ratio)
    ic_series = aligned["s"].rolling(20).corr(aligned["r"].shift(-1)).dropna()
    ir = ic_series.mean() / (ic_series.std() + 1e-10) * np.sqrt(252)

    return {
        "lead_k": lead_k,
        "n_obs": len(aligned),
        "direction_accuracy": float(direction_accuracy),
        "spearman_ic": float(ic),
        "ic_p_value": float(ic_pval),
        "information_ratio": float(ir),
        "quintile_returns": quintile_returns.to_dict(),
        "is_informative": ic_pval < 0.05 and direction_accuracy > 0.5,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Composite wrapper (backward-compatible)
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_stock_granger(
    sentiment_series: pd.Series,
    stock_returns: pd.Series,
    max_lag: int = 5,
) -> dict:
    """
    Full Granger analysis suite:
      - Bidirectional Granger tests
      - Lead/lag decomposition
      - Predictive scores at optimal lead
      - Stationarity diagnostics
    """
    sent_to_ret = run_granger_causality(sentiment_series, stock_returns, max_lag)
    ret_to_sent = run_granger_causality(stock_returns, sentiment_series, max_lag)

    lead_lag = sentiment_lead_lag_analysis(sentiment_series, stock_returns, max_lag)

    optimal_k = lead_lag["optimal_lead"] or 1
    pred_score = sentiment_predictive_score(sentiment_series, stock_returns, lead_k=optimal_k)

    return {
        "sentiment_causes_return": sent_to_ret,
        "return_causes_sentiment": ret_to_sent,
        "lead_lag": lead_lag,
        "predictive_score": pred_score,
        "stationarity": {
            "sentiment": check_stationarity(sentiment_series, "sentiment"),
            "returns": check_stationarity(stock_returns, "returns"),
        },
    }


def cross_correlation_analysis(
    series1: pd.Series,
    series2: pd.Series,
    max_lag: int = 10,
) -> pd.DataFrame:
    """Cross-correlation DataFrame (kept for dashboard compatibility)."""
    aligned = pd.concat([series1, series2], axis=1).dropna()
    s1 = (aligned.iloc[:, 0] - aligned.iloc[:, 0].mean()) / aligned.iloc[:, 0].std()
    s2 = (aligned.iloc[:, 1] - aligned.iloc[:, 1].mean()) / aligned.iloc[:, 1].std()

    rows = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            corr = s1.iloc[:lag].corr(s2.iloc[-lag:])
        elif lag > 0:
            corr = s1.iloc[lag:].corr(s2.iloc[:-lag])
        else:
            corr = s1.corr(s2)
        rows.append({"lag": lag, "correlation": corr})
    return pd.DataFrame(rows)
