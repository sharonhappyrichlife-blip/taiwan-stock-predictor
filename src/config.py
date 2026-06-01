"""
config.py

集中管理股票清單、產業設定與 Email 通知設定。
stock_list.json 由 fetch_stock_list.py 產生；
若檔案不存在則回退到內建的精簡清單，並印出提示。

Email 設定優先從環境變數或 .env 讀取，其次從此檔案的預設值。
請將真實憑證填入專案根目錄的 .env，不要硬寫在此檔案。
"""

import json
import os
from pathlib import Path

# 嘗試載入 .env（若安裝了 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


# ── Email 通知設定 ────────────────────────────────────────────────────────────
class EmailConfig:
    """Gmail SMTP 設定。從環境變數讀取，方便 CI/容器部署。"""

    # 寄件者 Gmail 帳號（完整地址，例如 yourname@gmail.com）
    SENDER: str = os.getenv("GMAIL_SENDER", "your_gmail@gmail.com")

    # Gmail 應用程式密碼（非登入密碼）
    # 產生方式：Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼
    APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "your_app_password_here")

    # 收件者（多個收件者以逗號分隔，例如 "a@x.com,b@y.com"）
    RECIPIENTS: str = os.getenv("GMAIL_RECIPIENTS", "recipient@example.com")

    # SMTP 伺服器（Gmail 固定值，一般不需修改）
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587

    @classmethod
    def recipient_list(cls) -> list[str]:
        return [r.strip() for r in cls.RECIPIENTS.split(",") if r.strip()]

    @classmethod
    def is_configured(cls) -> bool:
        """檢查是否已填入真實設定（非預設佔位值）。"""
        return (
            cls.SENDER != "your_gmail@gmail.com"
            and cls.APP_PASSWORD != "your_app_password_here"
            and "example.com" not in cls.RECIPIENTS
        )


# ── 監控設定 ──────────────────────────────────────────────────────────────────
class MonitorConfig:
    # 每次輪詢間隔（秒）
    POLL_INTERVAL_SECONDS: int = int(os.getenv("MONITOR_POLL_INTERVAL", "60"))

    # 單日漲跌幅觸發閾值（%）
    ALERT_RISE_PCT: float = float(os.getenv("MONITOR_ALERT_RISE_PCT", "5.0"))
    ALERT_FALL_PCT: float = float(os.getenv("MONITOR_ALERT_FALL_PCT", "-5.0"))

    # 每日摘要寄送時間（24h 格式，台灣收盤後）
    DAILY_SUMMARY_TIME: str = os.getenv("MONITOR_SUMMARY_TIME", "14:00")

    # 每日摘要排行榜顯示前 N 名
    SUMMARY_TOP_N: int = int(os.getenv("MONITOR_SUMMARY_TOP_N", "10"))

    # 警報批次等待秒數（收集同時觸發的多支股票，合併成一封信）
    BATCH_WINDOW_SECONDS: int = int(os.getenv("MONITOR_BATCH_WINDOW", "30"))

_STOCK_LIST_PATH = Path(__file__).parent.parent / "stock_list.json"

# 產業代碼對照表（與 fetch_stock_list.py 保持同步）
INDUSTRY_NAMES: dict[str, str] = {
    "24": "半導體",
    "25": "電腦及週邊",
    "26": "光電",
    "27": "通訊網路",
    "28": "電子零組件",
    "29": "電子設備",
    "30": "資訊服務",
    "31": "其他電子",
}

# 內建精簡清單（fallback，避免 stock_list.json 尚未產生時整個專案壞掉）
_BUILTIN_STOCKS: list[dict] = [
    {"code": "2330", "name": "台積電",  "industry_code": "24", "industry_name": "半導體",     "market": "TWSE"},
    {"code": "2454", "name": "聯發科",  "industry_code": "24", "industry_name": "半導體",     "market": "TWSE"},
    {"code": "2308", "name": "台達電",  "industry_code": "28", "industry_name": "電子零組件", "market": "TWSE"},
    {"code": "2317", "name": "鴻海",    "industry_code": "25", "industry_name": "電腦及週邊", "market": "TWSE"},
    {"code": "2382", "name": "廣達",    "industry_code": "25", "industry_name": "電腦及週邊", "market": "TWSE"},
    {"code": "2357", "name": "華碩",    "industry_code": "25", "industry_name": "電腦及週邊", "market": "TWSE"},
    {"code": "2303", "name": "聯電",    "industry_code": "24", "industry_name": "半導體",     "market": "TWSE"},
    {"code": "3034", "name": "聯詠",    "industry_code": "24", "industry_name": "半導體",     "market": "TWSE"},
    {"code": "2379", "name": "瑞昱",    "industry_code": "27", "industry_name": "通訊網路",   "market": "TWSE"},
    {"code": "2412", "name": "中華電",  "industry_code": "27", "industry_name": "通訊網路",   "market": "TWSE"},
]


def load_stock_list() -> list[dict]:
    """
    載入 stock_list.json；檔案不存在時使用內建清單並警告。
    回傳格式：[{"code", "name", "industry_code", "industry_name", "market"}, ...]
    """
    if _STOCK_LIST_PATH.exists():
        try:
            data = json.loads(_STOCK_LIST_PATH.read_text(encoding="utf-8"))
            stocks = data.get("stocks", [])
            if stocks:
                return stocks
        except Exception as e:
            print(f"[config] 讀取 stock_list.json 失敗：{e}，改用內建清單")
    else:
        print(
            "[config] stock_list.json 尚未產生，使用內建精簡清單。\n"
            "         請執行 `python fetch_stock_list.py` 產生完整清單。"
        )
    return _BUILTIN_STOCKS


def get_stock_dict() -> dict[str, str]:
    """回傳 {code: name} 格式，供下拉選單使用。"""
    return {s["code"]: s["name"] for s in load_stock_list()}


def get_stocks_by_industry(industry_code: str) -> list[dict]:
    """篩選特定產業代碼的股票。"""
    return [s for s in load_stock_list() if s.get("industry_code") == industry_code]


def get_stock_info(code: str) -> dict | None:
    """依代號取得單支股票資訊。"""
    for s in load_stock_list():
        if s["code"] == code:
            return s
    return None


def stock_list_metadata() -> dict:
    """回傳 stock_list.json 的 metadata（產生時間、總數等）。"""
    if not _STOCK_LIST_PATH.exists():
        return {"source": "builtin", "total": len(_BUILTIN_STOCKS)}
    try:
        data = json.loads(_STOCK_LIST_PATH.read_text(encoding="utf-8"))
        return {
            "source": "stock_list.json",
            "generated_at": data.get("generated_at", "unknown"),
            "total": data.get("total", 0),
            "path": str(_STOCK_LIST_PATH),
        }
    except Exception:
        return {"source": "builtin", "total": len(_BUILTIN_STOCKS)}
