import time

import numpy as np
import pandas as pd
import yfinance as yf

from .config import get_stock_dict, load_stock_list

# 動態從 stock_list.json 載入（若不存在則用內建清單）
TAIWAN_STOCKS: dict[str, str] = get_stock_dict()

TAIEX_SYMBOL = "^TWII"


def fetch_stock_data(symbol: str, period: str = "1y") -> pd.DataFrame:
    """Fetch historical OHLCV data for a Taiwan stock."""
    ticker = f"{symbol}.TW" if not symbol.startswith("^") else symbol
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        df.index.name = "date"
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return pd.DataFrame()


def fetch_multiple_stocks(symbols: list, period: str = "1y") -> dict:
    """Fetch data for multiple stocks."""
    result = {}
    for sym in symbols:
        df = fetch_stock_data(sym, period)
        if not df.empty:
            result[sym] = df
        time.sleep(0.3)
    return result


def get_all_stocks() -> list[dict]:
    """回傳完整股票清單（含產業資訊）。"""
    return load_stock_list()


def generate_mock_sentiment(dates: pd.DatetimeIndex, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic sentiment scores for demonstration."""
    np.random.seed(seed)
    n = len(dates)
    sentiment = np.zeros(n)
    sentiment[0] = 0.0
    for i in range(1, n):
        sentiment[i] = 0.7 * sentiment[i - 1] + np.random.normal(0, 0.3)
    sentiment = (sentiment - sentiment.min()) / (sentiment.max() - sentiment.min()) * 2 - 1
    return pd.DataFrame(
        {"sentiment": sentiment, "volume_sentiment": np.random.uniform(-1, 1, n)},
        index=dates,
    )
