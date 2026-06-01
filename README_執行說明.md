# 台股情緒分析監控系統 — 本機執行說明

本說明引導您從零開始，在自己的電腦上完整執行本專案，
包含股票監控警報、每日 Email 摘要與技術分析儀表板。

---

## 目錄

1. [系統需求](#1-系統需求)
2. [複製專案到本機](#2-複製專案到本機)
3. [安裝 Python 與必要套件](#3-安裝-python-與必要套件)
4. [設定 Gmail 應用程式密碼](#4-設定-gmail-應用程式密碼)
5. [填寫 .env 設定檔](#5-填寫-env-設定檔)
6. [抓取最新台股清單](#6-抓取最新台股清單)
7. [發送測試信確認郵件正常](#7-發送測試信確認郵件正常)
8. [啟動每日自動監控排程](#8-啟動每日自動監控排程)
9. [開啟技術分析儀表板（選用）](#9-開啟技術分析儀表板選用)
10. [常見問題](#10-常見問題)

---

## 1. 系統需求

| 項目 | 最低需求 |
|------|---------|
| 作業系統 | Windows 10 / macOS 12 / Ubuntu 20.04 以上 |
| Python | **3.11 以上**（必須，低於此版本部分語法不支援） |
| 硬碟空間 | 500 MB 以上（套件安裝用） |
| 網路 | 需能連線至 Yahoo Finance、Gmail SMTP |
| Gmail | 需開啟兩步驟驗證並產生應用程式密碼 |

---

## 2. 複製專案到本機

### 步驟 2-1｜安裝 Git（已安裝可略過）

- **Windows**：下載 [git-scm.com](https://git-scm.com/download/win) 並安裝
- **macOS**：開啟終端機，執行 `xcode-select --install`
- **Ubuntu / Debian**：`sudo apt install git`

### 步驟 2-2｜複製專案

開啟終端機（Windows 請用「命令提示字元」或「PowerShell」），執行：

```bash
git clone https://github.com/sharonhappyrichlife-blip/taiwan-stock-predictor.git
cd taiwan-stock-predictor
```

> 之後若要取得最新更新，在同一個資料夾執行：
> ```bash
> git pull origin main
> ```

---

## 3. 安裝 Python 與必要套件

### 步驟 3-1｜確認 Python 版本

```bash
python --version
# 需顯示 Python 3.11.x 或以上
```

若版本不符或尚未安裝，請至 [python.org/downloads](https://www.python.org/downloads/) 下載 3.11 以上版本。

> **Windows 注意**：安裝時請勾選 **「Add Python to PATH」**，否則終端機找不到 python 指令。

### 步驟 3-2｜建立虛擬環境（強烈建議）

```bash
# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境
# Windows：
.venv\Scripts\activate
# macOS / Linux：
source .venv/bin/activate
```

啟動後，命令提示字元前面會出現 `(.venv)` 字樣，表示已進入虛擬環境。

> 每次開新的終端機視窗都需要重新執行啟動虛擬環境的指令。

### 步驟 3-3｜安裝所有套件

```bash
pip install -r requirements.txt
```

安裝過程約需 2～5 分鐘。完成後確認無錯誤訊息。

---

## 4. 設定 Gmail 應用程式密碼

> **重要**：監控程式使用的是「應用程式密碼」，**不是** 您的 Gmail 登入密碼。
> 兩者不同，請勿混淆。

### 步驟 4-1｜開啟兩步驟驗證（已開啟可略過）

1. 前往 [myaccount.google.com](https://myaccount.google.com)
2. 點選左側「**安全性**」
3. 找到「**兩步驟驗證**」→ 按照指示開啟

### 步驟 4-2｜產生應用程式密碼

1. 在「安全性」頁面，搜尋框輸入「**應用程式密碼**」
2. 點進去後，在「選取應用程式」下拉選單選「**其他（自訂名稱）**」
3. 名稱填入：`台股監控`
4. 點擊「**產生**」
5. Google 顯示一組 **16 碼密碼**（含空格，如 `duey palw iywo qngp`）
6. **立即複製並保存**，此密碼只會顯示一次

---

## 5. 填寫 .env 設定檔

### 步驟 5-1｜從範本建立 .env

```bash
cp .env.example .env
```

### 步驟 5-2｜編輯 .env 填入真實設定

用任意文字編輯器（記事本、VS Code 均可）開啟 `.env`，
找到以下三行並填入您的資料：

```ini
# 寄件者：您的 Gmail 地址
GMAIL_SENDER=yourname@gmail.com

# 應用程式密碼（步驟 4-2 取得的 16 碼，含空格）
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# 收件者：收到警報通知的信箱（可填自己的，多個用逗號分隔）
GMAIL_RECIPIENTS=yourname@gmail.com
```

填寫範例：

```ini
GMAIL_SENDER=sharon123@gmail.com
GMAIL_APP_PASSWORD=duey palw iywo qngp
GMAIL_RECIPIENTS=sharon123@gmail.com
```

### 選用：調整監控閾值

預設值已適合一般使用，如需調整可取消以下行的 `#` 並修改數值：

```ini
# 單日漲幅超過此 % 才發警報（預設 5.0）
MONITOR_ALERT_RISE_PCT=5.0

# 單日跌幅超過此 % 才發警報（預設 -5.0）
MONITOR_ALERT_FALL_PCT=-5.0

# 每日摘要寄送時間，台灣收盤後（預設 14:00）
MONITOR_SUMMARY_TIME=14:00

# 每日摘要顯示漲跌排行前幾名（預設 10）
MONITOR_SUMMARY_TOP_N=10
```

> **安全提醒**：`.env` 已被 `.gitignore` 排除，不會被 `git push` 上傳，您的密碼不會外洩。

---

## 6. 抓取最新台股清單

執行以下指令，自動從證交所與櫃買中心 API 抓取所有電子類股（產業代碼 24–31）：

```bash
python fetch_stock_list.py
```

成功後會產生 `stock_list.json`，輸出類似：

```
============================================================
台灣電子類股清單抓取程式
目標產業：24(半導體), 25(電腦及週邊), 26(光電), ...
============================================================
[TWSE] 抓取產業分類資料...
[TWSE] 產業分類 API 電子類股：186 支
[TPEx] 抓取上櫃股票清單...
[TPEx] 篩選後電子類股：243 支

── 篩選結果 ──
  24 半導體：87 支
  25 電腦及週邊：52 支
  ...
  合計：350 支

已寫入：stock_list.json  (350 支股票)
```

> 若網路不穩定導致部分 API 失敗，程式會自動 fallback 到內建的 10 支精簡清單，
> 監控程式仍可正常運作，不影響後續步驟。

---

## 7. 發送測試信確認郵件正常

執行以下指令，程式會自動寄出一封**警報測試信**和一封**每日摘要測試信**：

```bash
python monitor.py --test-email
```

### 預期輸出（成功）

```
2025-06-01 14:30:00 [INFO] 發送測試警報郵件...
[email] 已寄出：【台股警報】2 支股票觸發條件 — 最大漲幅 台積電(2330) +11.2%
2025-06-01 14:30:02 [INFO] 發送測試每日摘要郵件...
[email] 已寄出：【台股每日摘要】2025/06/01 電子類股漲跌排行
2025-06-01 14:30:04 [INFO] ✅ 測試郵件全部寄出成功！
```

收到兩封郵件後，即代表設定正確，可以進入下一步。

### 常見錯誤排除

| 錯誤訊息 | 原因 | 解法 |
|----------|------|------|
| `SMTPAuthenticationError` | 密碼錯誤或使用了登入密碼 | 確認填入的是「應用程式密碼」（16碼） |
| `尚未設定 Gmail 憑證` | .env 未填寫或仍是預設佔位值 | 重新檢查 .env 三個欄位 |
| `Connection refused` | 防火牆封鎖 SMTP 連接埠 587 | 確認網路允許對外連線，或暫時關閉防毒軟體 |

---

## 8. 啟動每日自動監控排程

### 一般啟動

```bash
python monitor.py
```

啟動後會看到：

```
2025-06-01 09:00:00 [INFO] 載入 350 支股票
2025-06-01 09:00:00 [INFO] 監控啟動 | 股票：350 支 | 輪詢間隔：60s | 警報閾值：漲 +5.0% / 跌 -5.0% | 每日摘要：14:00
2025-06-01 09:00:01 [INFO] 輪詢 350 支股票...
```

- 每 **60 秒**自動抓取一次最新報價
- 漲跌超過閾值立即發送警報 Email
- 每日 **14:00** 自動寄出收盤摘要
- 按 `Ctrl + C` 結束程式

### 乾跑模式（不寄信，只看 log）

適合想觀察程式行為但不想收到真實郵件時使用：

```bash
python monitor.py --dry-run
```

---

### 讓監控在背景持續執行（電腦關機不中斷）

#### Windows — 使用工作排程器

1. 搜尋「**工作排程器**」→「建立基本工作」
2. 觸發程式：「**每天**」→ 設定時間（建議盤前 08:30）
3. 動作：「**啟動程式**」
   - 程式：`C:\路徑\python.exe`
   - 引數：`monitor.py`
   - 起始位置：`C:\你的專案路徑\taiwan-stock-predictor`
4. 完成

#### macOS — 使用 launchd

建立設定檔 `~/Library/LaunchAgents/com.taiwan.monitor.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.taiwan.monitor</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/你的名字/taiwan-stock-predictor/monitor.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/你的名字/taiwan-stock-predictor</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/taiwan-monitor.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/taiwan-monitor-error.log</string>
</dict>
</plist>
```

載入並啟動：

```bash
launchctl load ~/Library/LaunchAgents/com.taiwan.monitor.plist
```

#### Linux — 使用 systemd

建立服務檔案 `/etc/systemd/system/taiwan-monitor.service`：

```ini
[Unit]
Description=Taiwan Stock Monitor
After=network.target

[Service]
Type=simple
User=你的用戶名
WorkingDirectory=/home/你的用戶名/taiwan-stock-predictor
ExecStart=/home/你的用戶名/taiwan-stock-predictor/.venv/bin/python monitor.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

啟動並設定開機自啟：

```bash
sudo systemctl daemon-reload
sudo systemctl enable taiwan-monitor
sudo systemctl start taiwan-monitor

# 查看即時 log
sudo journalctl -u taiwan-monitor -f
```

---

## 9. 開啟技術分析儀表板（選用）

監控程式與儀表板可以**同時執行**，互不干擾。

```bash
streamlit run dashboard.py
```

瀏覽器會自動開啟，網址為 `http://localhost:8501`

儀表板功能：
- **技術分析**：K線圖、均線、MACD、RSI、布林通道
- **情緒分析**：新聞情緒趨勢、情緒分佈
- **格蘭傑因果**：情緒領先/落後分析、滾動視窗檢定、預測力評分
- **訊號摘要**：自動產生買賣訊號

---

## 10. 常見問題

**Q：可以同時監控幾支股票？**
> 預設監控 `stock_list.json` 內所有電子類股（約 300～400 支）。
> 若覺得太多，可在 `monitor.py` 啟動前先用 `fetch_stock_list.py --dry-run` 確認清單。

**Q：警報同一支股票一天會收到幾封信？**
> 每支股票每天只觸發一次警報（避免當天反覆震盪導致洗版）。
> 且同一批次視窗（30 秒）內觸發的多支股票會合併成一封信。

**Q：stock_list.json 多久更新一次？**
> 不會自動更新，需手動執行 `python fetch_stock_list.py`。
> 建議每月執行一次以納入新上市股票。

**Q：收盤後還在運行會抓到假資料嗎？**
> Yahoo Finance 在非交易時段回傳的是最後成交價，不會產生錯誤警報，
> 因為漲跌幅計算基準是前一日收盤，盤後數值不變。

**Q：Python 版本是 3.10 可以嗎？**
> 不行。本專案使用了 `type | None`、`match` 等 3.10+ 語法，
> 以及 `zoneinfo`（3.9+）與 `tuple[str, str]` 型別提示（3.9+），
> 建議使用 **Python 3.11** 以確保完全相容。

---

## 專案檔案結構

```
taiwan-stock-predictor/
├── monitor.py              # 主監控程式（每日自動排程）
├── dashboard.py            # Streamlit 技術分析儀表板
├── fetch_stock_list.py     # 從證交所/櫃買抓取股票清單
├── stock_list.json         # 產生的股票清單（執行 fetch_stock_list.py 後出現）
├── .env                    # Gmail 設定（不會被 git 上傳）
├── .env.example            # 設定範本
├── requirements.txt        # 套件清單
└── src/
    ├── config.py           # 集中設定（Email、監控閾值、股票清單讀取）
    ├── data_fetcher.py     # Yahoo Finance 股票資料抓取
    ├── email_notifier.py   # Gmail SMTP 郵件發送
    ├── granger_analysis.py # 格蘭傑因果分析
    ├── sentiment_analyzer.py  # 中文財經情緒分析
    └── technical_indicators.py  # 技術指標計算
```

---

*如有問題，請在 GitHub Issues 回報。*
