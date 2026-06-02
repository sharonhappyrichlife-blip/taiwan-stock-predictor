"""
tda_analysis.py

拓樸資料分析（TDA）模組。
使用 ripser 對股票收盤價時間序列計算 Persistent Homology，
萃取持久性特徵（max/mean persistence、entropy、Betti 數），
並可與 Granger 情緒特徵合併成完整特徵向量。

執行方式：
  python src/tda_analysis.py --code 2330            # 單支
  python src/tda_analysis.py                         # 全部，輸出 tda_features.json
  python src/tda_analysis.py --max-stocks 10 --output tda_test.json
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from ripser import ripser
    HAS_RIPSER = True
except ImportError:
    HAS_RIPSER = False

try:
    from .data_fetcher import fetch_stock_data, get_all_stocks
    from .config import get_stock_dict
except ImportError:
    from data_fetcher import fetch_stock_data, get_all_stocks
    from config import get_stock_dict


# ── 點雲建構 ──────────────────────────────────────────────────────────────────

def normalize_series(series: np.ndarray) -> np.ndarray:
    """Min-max 正規化至 [0, 1]。"""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return np.zeros_like(series, dtype=float)
    return (series - lo) / (hi - lo)


def sliding_window_embedding(series: np.ndarray, window: int = 20, stride: int = 2) -> np.ndarray:
    """
    滑動視窗嵌入：將 1D 時間序列轉為 window 維點雲。
    stride > 1 可降低點數、加快計算。
    Returns ndarray of shape (n_points, window).
    """
    n = len(series)
    if n < window:
        return np.empty((0, window), dtype=float)
    idx = range(0, n - window + 1, stride)
    return np.array([series[i:i + window] for i in idx], dtype=float)


# ── 持久性特徵萃取 ────────────────────────────────────────────────────────────

def _finite_pairs(dgm: np.ndarray) -> np.ndarray:
    """移除持久性圖中死亡值為無限大的點（最後存活的連通元件）。"""
    if len(dgm) == 0:
        return dgm
    return dgm[dgm[:, 1] != np.inf]


def persistence_features(dgm: np.ndarray) -> dict:
    """
    從持久性圖萃取統計特徵：
    - max_persistence   : 最大持久性（最顯著的拓樸特徵）
    - mean_persistence  : 平均持久性
    - persistence_entropy : 持久性熵（特徵多樣性指標）
    - betti_number      : 存活特徵數（持久性 > 0 的點數）
    - total_persistence : 總持久性
    """
    dgm = _finite_pairs(dgm)
    zero = dict(max_persistence=0.0, mean_persistence=0.0,
                persistence_entropy=0.0, betti_number=0, total_persistence=0.0)
    if len(dgm) == 0:
        return zero
    lifetimes = dgm[:, 1] - dgm[:, 0]
    lifetimes = lifetimes[lifetimes > 1e-10]
    if len(lifetimes) == 0:
        return zero
    total = float(lifetimes.sum())
    probs = lifetimes / total
    entropy = float(-np.sum(probs * np.log(probs + 1e-12)))
    return dict(
        max_persistence=float(lifetimes.max()),
        mean_persistence=float(lifetimes.mean()),
        persistence_entropy=round(entropy, 6),
        betti_number=int(len(lifetimes)),
        total_persistence=round(total, 6),
    )


def _top_bars(dgm: np.ndarray, n: int = 30) -> list[list[float]]:
    """取持久性最高的 n 條條碼，回傳 [[birth, death], ...]（已正規化至 [0,1]）。"""
    dgm = _finite_pairs(dgm)
    if len(dgm) == 0:
        return []
    order = np.argsort(dgm[:, 1] - dgm[:, 0])[::-1][:n]
    return [[round(b, 6), round(d, 6)] for b, d in dgm[order]]


# ── 主要分析函式 ──────────────────────────────────────────────────────────────

def analyze_stock_tda(
    code: str,
    closes: np.ndarray,
    window: int = 20,
    max_dim: int = 1,
    stride: int = 2,
) -> dict:
    """
    對單支股票的收盤價序列執行 TDA 分析。

    Parameters
    ----------
    code    : 股票代號（純記錄用）
    closes  : 收盤價 ndarray（需 ≥ window+5 筆）
    window  : 滑動視窗維度（預設 20 天）
    max_dim : 計算的最高同調維度（0=H0 only, 1=H0+H1）
    stride  : 點雲取樣步距（stride=2 每隔一天取一點）

    Returns dict with keys:
      code, h0, h1, h0_bars, h1_bars, analyzed_at, n_points, error
    """
    result: dict = {
        "code": code,
        "h0": {}, "h1": {},
        "h0_bars": [], "h1_bars": [],
        "analyzed_at": datetime.now().isoformat(),
        "n_points": 0,
        "error": None,
    }

    if not HAS_RIPSER:
        result["error"] = "ripser 未安裝，請執行 pip install ripser"
        return result

    closes = np.asarray(closes, dtype=float)
    min_required = window + 5
    if len(closes) < min_required:
        result["error"] = f"資料不足（需 ≥ {min_required} 筆，實際 {len(closes)} 筆）"
        return result

    norm = normalize_series(closes)
    cloud = sliding_window_embedding(norm, window=window, stride=stride)
    result["n_points"] = len(cloud)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dgms = ripser(cloud, maxdim=max_dim)["dgms"]
    except Exception as e:
        result["error"] = str(e)
        return result

    h0 = dgms[0]
    h1 = dgms[1] if len(dgms) > 1 else np.empty((0, 2))

    result["h0"] = persistence_features(h0)
    result["h1"] = persistence_features(h1)
    result["h0_bars"] = _top_bars(h0)
    result["h1_bars"] = _top_bars(h1)
    return result


# ── 批次分析 ─────────────────────────────────────────────────────────────────

def analyze_all_stocks_tda(
    period: str = "1y",
    window: int = 20,
    output_path: str = "tda_features.json",
    max_stocks: int | None = None,
) -> dict:
    """
    批次分析所有股票，結果寫入 JSON。

    Returns {code: result_dict, ...}。
    """
    stocks = get_all_stocks()
    if max_stocks:
        stocks = stocks[:max_stocks]

    all_features: dict = {}
    for i, s in enumerate(stocks, 1):
        code = s["code"]
        print(f"[TDA] ({i:3}/{len(stocks)}) {code} {s.get('name',''):8}", end="  ")
        df = fetch_stock_data(code, period=period)
        if df.empty or "close" not in df.columns:
            print("資料不足，略過")
            continue
        closes = df["close"].dropna().to_numpy()
        feat = analyze_stock_tda(code, closes, window=window)
        feat["name"] = s.get("name", "")
        feat["industry_code"] = s.get("industry_code", "")
        all_features[code] = feat
        if feat.get("error"):
            print(f"錯誤：{feat['error']}")
        else:
            print(
                f"H0 betti={feat['h0']['betti_number']:3d}  "
                f"H1 betti={feat['h1']['betti_number']:3d}  "
                f"點雲={feat['n_points']}點"
            )

    output = {
        "generated_at": datetime.now().isoformat(),
        "window": window,
        "total": len(all_features),
        "stocks": all_features,
    }
    Path(output_path).write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[TDA] 完成，共 {len(all_features)} 支，已儲存至 {output_path}")
    return all_features


# ── 與 Granger 特徵合併 ───────────────────────────────────────────────────────

def merge_with_granger(
    tda_features: dict,
    granger_df: pd.DataFrame,
    tda_prefix: str = "tda_",
) -> pd.DataFrame:
    """
    將 TDA 特徵展平後合併進 Granger 分析 DataFrame。

    granger_df 需有 "code" 欄位。
    產生的新欄位形如 tda_h0_max_persistence, tda_h1_betti_number, ...
    """
    rows = []
    for code, feat in tda_features.items():
        row: dict = {"code": code}
        for dim in ("h0", "h1"):
            for k, v in feat.get(dim, {}).items():
                row[f"{tda_prefix}{dim}_{k}"] = v
        rows.append(row)

    tda_df = pd.DataFrame(rows)
    if granger_df.empty or "code" not in granger_df.columns:
        return tda_df
    return granger_df.merge(tda_df, on="code", how="left")


# ── 特徵重要性摘要（供 Streamlit dashboard 使用）─────────────────────────────

def tda_summary_table(tda_features: dict) -> pd.DataFrame:
    """
    將所有股票的 TDA 特徵整理成 DataFrame，方便排序與視覺化。

    欄位：code, name, h0_max, h0_entropy, h0_betti, h1_max, h1_entropy, h1_betti
    """
    rows = []
    for code, feat in tda_features.items():
        if feat.get("error"):
            continue
        rows.append({
            "code": code,
            "name": feat.get("name", ""),
            "h0_max_persistence": feat["h0"].get("max_persistence", 0),
            "h0_persistence_entropy": feat["h0"].get("persistence_entropy", 0),
            "h0_betti": feat["h0"].get("betti_number", 0),
            "h1_max_persistence": feat["h1"].get("max_persistence", 0),
            "h1_persistence_entropy": feat["h1"].get("persistence_entropy", 0),
            "h1_betti": feat["h1"].get("betti_number", 0),
        })
    return pd.DataFrame(rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    sys.path.insert(0, str(Path(__file__).parent))

    parser = argparse.ArgumentParser(description="台股拓樸資料分析（TDA）")
    parser.add_argument("--code", default=None, help="單支股票代號（不填則分析全部）")
    parser.add_argument("--period", default="1y", help="資料期間，例如 1y, 2y（預設 1y）")
    parser.add_argument("--window", type=int, default=20, help="滑動視窗大小（預設 20）")
    parser.add_argument("--output", default="tda_features.json", help="輸出 JSON 路徑（預設 tda_features.json）")
    parser.add_argument("--max-stocks", type=int, default=None, help="最多分析幾支（測試用）")
    parser.add_argument("--stride", type=int, default=2, help="點雲取樣步距（預設 2）")
    args = parser.parse_args()

    if not HAS_RIPSER:
        print("錯誤：ripser 未安裝，請執行：pip install ripser persim")
        sys.exit(1)

    if args.code:
        # 單支分析並印出 JSON
        sys.path.insert(0, "src")
        from data_fetcher import fetch_stock_data  # noqa: F811
        df = fetch_stock_data(args.code, period=args.period)
        if df.empty:
            print(f"無法取得 {args.code} 的資料")
            sys.exit(1)
        result = analyze_stock_tda(
            args.code, df["close"].dropna().to_numpy(),
            window=args.window, stride=args.stride,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        analyze_all_stocks_tda(
            period=args.period,
            window=args.window,
            output_path=args.output,
            max_stocks=args.max_stocks,
        )
