import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

TAIWAN_STOCKS = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2308": "台達電",
    "2382": "廣達",
    "2881": "富邦金",
    "2882": "國泰金",
    "1301": "台塑",
    "1303": "南亞",
    "2412": "中華電",
}

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


def generate_mock_sentiment(dates: pd.DatetimeIndex, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic sentiment scores for demonstration."""
    np.random.seed(seed)
    n = len(dates)
    # Simulate AR(1) process for realistic sentiment dynamics
    sentiment = np.zeros(n)
    sentiment[0] = 0.0
    for i in range(1, n):
        sentiment[i] = 0.7 * sentiment[i-1] + np.random.normal(0, 0.3)
    sentiment = (sentiment - sentiment.min()) / (sentiment.max() - sentiment.min()) * 2 - 1
    return pd.DataFrame({"sentiment": sentiment, "volume_sentiment": np.random.uniform(-1, 1, n)}, index=dates)
