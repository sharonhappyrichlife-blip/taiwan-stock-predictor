import pandas as pd
import numpy as np


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to OHLCV DataFrame."""
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving Averages
    df["ma5"] = close.rolling(5).mean()
    df["ma10"] = close.rolling(10).mean()
    df["ma20"] = close.rolling(20).mean()
    df["ma60"] = close.rolling(60).mean()
    df["ema12"] = close.ewm(span=12, adjust=False).mean()
    df["ema26"] = close.ewm(span=26, adjust=False).mean()

    # MACD
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # RSI
    df["rsi"] = _rsi(close, 14)

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_mid"] = bb_mid
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    # Stochastic
    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    df["stoch_k"] = 100 * (close - low14) / (high14 - low14 + 1e-10)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # ATR
    df["atr"] = _atr(high, low, close, 14)

    # OBV
    df["obv"] = _obv(close, volume)

    # Volume MA
    df["vol_ma20"] = volume.rolling(20).mean()
    df["vol_ratio"] = volume / df["vol_ma20"]

    # Returns
    df["returns"] = close.pct_change()
    df["log_returns"] = np.log(close / close.shift(1))

    # Price momentum
    df["momentum_5"] = close / close.shift(5) - 1
    df["momentum_20"] = close / close.shift(20) - 1

    return df


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - 100 / (1 + rs)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def get_signal_summary(df: pd.DataFrame) -> dict:
    """Generate buy/sell signal summary based on indicators."""
    latest = df.iloc[-1]
    signals = {}

    # MA trend
    if latest["ma5"] > latest["ma20"] > latest["ma60"]:
        signals["ma_trend"] = ("bullish", "短期均線多頭排列")
    elif latest["ma5"] < latest["ma20"] < latest["ma60"]:
        signals["ma_trend"] = ("bearish", "短期均線空頭排列")
    else:
        signals["ma_trend"] = ("neutral", "均線糾結")

    # RSI
    rsi = latest["rsi"]
    if rsi > 70:
        signals["rsi"] = ("overbought", f"RSI超買 ({rsi:.1f})")
    elif rsi < 30:
        signals["rsi"] = ("oversold", f"RSI超賣 ({rsi:.1f})")
    else:
        signals["rsi"] = ("neutral", f"RSI中性 ({rsi:.1f})")

    # MACD
    if latest["macd"] > latest["macd_signal"] and latest["macd_hist"] > 0:
        signals["macd"] = ("bullish", "MACD黃金交叉")
    elif latest["macd"] < latest["macd_signal"] and latest["macd_hist"] < 0:
        signals["macd"] = ("bearish", "MACD死亡交叉")
    else:
        signals["macd"] = ("neutral", "MACD中性")

    # Bollinger
    close = latest["close"]
    if close > latest["bb_upper"]:
        signals["bollinger"] = ("overbought", "突破布林上軌")
    elif close < latest["bb_lower"]:
        signals["bollinger"] = ("oversold", "跌破布林下軌")
    else:
        signals["bollinger"] = ("neutral", "布林通道中性")

    return signals
