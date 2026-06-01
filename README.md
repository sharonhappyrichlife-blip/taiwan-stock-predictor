# 台股情緒分析預測系統

整合技術指標、情緒分析與格蘭傑因果檢定的台股互動式分析儀表板。

## 功能特色

- **技術分析儀表板**：K線圖、MA5/20/60均線、MACD、RSI、布林通道、KD隨機指標、ATR
- **情緒分析**：基於關鍵詞的中文財經新聞情緒評分、情緒動能、情緒分佈
- **格蘭傑因果分析**：檢驗情緒是否能 Granger-cause 股價報酬，含 P 值圖與互相關分析
- **訊號摘要**：自動綜合技術指標產生看多/看空/中性訊號

## 快速開始

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## 模組說明

| 模組 | 說明 |
|------|------|
| `src/data_fetcher.py` | 台股 OHLCV 資料抓取（Yahoo Finance） |
| `src/technical_indicators.py` | 技術指標計算（MA、MACD、RSI、BB、ATR、OBV…） |
| `src/sentiment_analyzer.py` | 中文財經關鍵詞情緒評分 |
| `src/granger_analysis.py` | 格蘭傑因果統計檢定、VAR 模型、互相關分析 |
| `dashboard.py` | Streamlit 互動式儀表板主程式 |

## 支援股票

台積電(2330)、鴻海(2317)、聯發科(2454)、台達電(2308)、廣達(2382)、
富邦金(2881)、國泰金(2882)、台塑(1301)、南亞(1303)、中華電(2412)
