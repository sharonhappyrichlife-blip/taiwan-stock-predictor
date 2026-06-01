import re
import pandas as pd
import numpy as np

# Simple keyword-based sentiment lexicon for Taiwan financial news
POSITIVE_WORDS = [
    "上漲", "漲停", "利多", "突破", "強勢", "創高", "買進", "看多",
    "獲利", "成長", "增加", "擴張", "超預期", "優於", "轉盈", "回升",
    "反彈", "買超", "外資買", "投信買", "法人買", "主力進場",
]

NEGATIVE_WORDS = [
    "下跌", "跌停", "利空", "跌破", "弱勢", "創低", "賣出", "看空",
    "虧損", "衰退", "減少", "縮減", "低於預期", "劣於", "轉虧", "回落",
    "急殺", "賣超", "外資賣", "投信賣", "法人賣", "主力出貨",
]

INTENSIFIERS = ["大幅", "急速", "劇烈", "顯著", "明顯"]
NEGATORS = ["不", "未", "沒有", "否認"]


def compute_text_sentiment(text: str) -> float:
    """
    Rule-based sentiment score for Chinese financial text.
    Returns score in [-1, 1].
    """
    if not text or not isinstance(text, str):
        return 0.0

    score = 0.0
    for word in POSITIVE_WORDS:
        count = text.count(word)
        score += count * 1.0

    for word in NEGATIVE_WORDS:
        count = text.count(word)
        score -= count * 1.0

    # Intensifiers amplify
    for word in INTENSIFIERS:
        if word in text:
            score *= 1.3

    # Simple negation: flip if negator precedes sentiment word
    for neg in NEGATORS:
        if neg in text:
            score *= -0.8

    # Normalize to [-1, 1]
    return float(np.tanh(score / 3))


def analyze_news_batch(news_list: list) -> pd.DataFrame:
    """Analyze a list of news dicts with 'date', 'title', 'content'."""
    records = []
    for item in news_list:
        title_score = compute_text_sentiment(item.get("title", ""))
        content_score = compute_text_sentiment(item.get("content", ""))
        combined = 0.6 * title_score + 0.4 * content_score
        records.append({
            "date": item.get("date"),
            "title": item.get("title", ""),
            "sentiment": combined,
            "title_sentiment": title_score,
            "content_sentiment": content_score,
        })
    df = pd.DataFrame(records)
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
    return df


def aggregate_daily_sentiment(sentiment_df: pd.DataFrame) -> pd.Series:
    """Aggregate multiple news sentiments per day into single daily score."""
    if sentiment_df.empty:
        return pd.Series(dtype=float)
    return sentiment_df["sentiment"].resample("D").mean()


def sentiment_momentum(daily_sentiment: pd.Series, window: int = 5) -> pd.Series:
    """Rolling mean of sentiment as momentum indicator."""
    return daily_sentiment.rolling(window, min_periods=1).mean()


def generate_sample_news(stock_name: str, dates: pd.DatetimeIndex) -> list:
    """Generate sample news data for demonstration."""
    np.random.seed(hash(stock_name) % 2**31)
    templates = [
        f"{stock_name}今日{{direction}}，法人{{action}}",
        f"分析師看{{outlook}}{stock_name}，目標價{{action}}",
        f"{stock_name}營收{{result}}，外資{{reaction}}",
        f"市場消息：{stock_name}{{event}}",
    ]
    direction_pos = ["上漲", "強勢回升", "突破壓力區"]
    direction_neg = ["下跌", "弱勢整理", "跌破支撐"]
    action_pos = ["買超", "積極買進", "上調"]
    action_neg = ["賣超", "調降", "減碼"]

    news = []
    for date in dates:
        if np.random.random() > 0.3:
            is_pos = np.random.random() > 0.45
            template = np.random.choice(templates)
            if is_pos:
                title = template.format(
                    direction=np.random.choice(direction_pos),
                    action=np.random.choice(action_pos),
                    outlook="多",
                    result="創新高",
                    reaction="積極買超",
                    event="獲利超預期",
                )
            else:
                title = template.format(
                    direction=np.random.choice(direction_neg),
                    action=np.random.choice(action_neg),
                    outlook="空",
                    result="低於預期",
                    reaction="連續賣超",
                    event="傳出利空消息",
                )
            news.append({"date": date, "title": title, "content": title})
    return news
