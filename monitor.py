#!/usr/bin/env python3
"""
monitor.py

台灣電子類股即時監控程式。
- 每分鐘輪詢所有監控中股票的最新報價
- 漲跌幅超過閾值時批次合併成一封警報 Email
- 每日 14:00（台灣時間）自動寄送每日摘要 Email
- 從 stock_list.json 動態載入股票清單，新上市股票不會漏掉

用法：
    python monitor.py                # 啟動監控
    python monitor.py --test-email   # 發送測試信，確認 Gmail 設定正確
    python monitor.py --dry-run      # 只印出警報，不實際寄信
"""

import argparse
import logging
import signal
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

import schedule
import yfinance as yf

sys.path.insert(0, "src")

from config import EmailConfig, MonitorConfig
from data_fetcher import get_all_stocks
from email_notifier import send_alert_email, send_daily_summary_email

TZ_TAIPEI = ZoneInfo("Asia/Taipei")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("monitor")


# ── 資料結構 ──────────────────────────────────────────────────────────────────

class StockSnapshot:
    """儲存單支股票的當日狀態。"""

    def __init__(self, code: str, name: str, industry_name: str):
        self.code = code
        self.name = name
        self.industry_name = industry_name
        self.price: float = 0.0
        self.prev_close: float = 0.0
        self.change_pct: float = 0.0
        self.alert_count: int = 0
        self.last_updated: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "industry_name": self.industry_name,
            "price": self.price,
            "prev_close": self.prev_close,
            "change_pct": self.change_pct,
            "alert_count": self.alert_count,
        }


# ── 報價抓取 ──────────────────────────────────────────────────────────────────

def _fetch_quote(code: str) -> dict | None:
    """
    從 yfinance 取得單支股票最新報價。
    回傳 {"price", "prev_close", "change_pct"}，失敗回傳 None。
    """
    ticker_sym = f"{code}.TW"
    try:
        ticker = yf.Ticker(ticker_sym)
        info = ticker.fast_info
        price = float(info.last_price or 0)
        prev_close = float(info.previous_close or 0)
        if price <= 0 or prev_close <= 0:
            return None
        change_pct = (price - prev_close) / prev_close * 100
        return {"price": price, "prev_close": prev_close, "change_pct": change_pct}
    except Exception as e:
        log.debug(f"[{code}] 報價抓取失敗：{e}")
        return None


def _fetch_quotes_batch(codes: list[str]) -> dict[str, dict]:
    """
    批次抓取多支股票報價（yfinance download，較省 API 呼叫次數）。
    """
    if not codes:
        return {}
    symbols = [f"{c}.TW" for c in codes]
    try:
        import pandas as pd
        df = yf.download(
            " ".join(symbols),
            period="2d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
        result = {}
        for code, sym in zip(codes, symbols):
            try:
                if len(codes) == 1:
                    close = df["Close"].dropna()
                else:
                    close = df[sym]["Close"].dropna()
                if len(close) < 2:
                    continue
                price = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                result[code] = {
                    "price": price,
                    "prev_close": prev,
                    "change_pct": (price - prev) / prev * 100,
                }
            except Exception:
                pass
        return result
    except Exception as e:
        log.warning(f"批次報價失敗，改用逐支抓取：{e}")
        result = {}
        for code in codes:
            q = _fetch_quote(code)
            if q:
                result[code] = q
            time.sleep(0.2)
        return result


# ── 警報批次緩衝 ──────────────────────────────────────────────────────────────

class AlertBatcher:
    """
    收集一個批次視窗內的所有觸發警報，時間到後合併成一封 Email。
    """

    def __init__(self, window_seconds: int, dry_run: bool = False):
        self._window = window_seconds
        self._dry_run = dry_run
        self._pending: list[dict] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def add(self, alert: dict):
        with self._lock:
            self._pending.append(alert)
            if self._timer is None:
                self._timer = threading.Timer(self._window, self._flush)
                self._timer.daemon = True
                self._timer.start()
                log.info(f"[batcher] 批次視窗開啟 ({self._window}s)，等待更多觸發...")

    def _flush(self):
        with self._lock:
            alerts = self._pending.copy()
            self._pending.clear()
            self._timer = None

        if not alerts:
            return

        log.info(f"[batcher] 寄出警報郵件，共 {len(alerts)} 支股票觸發")
        if self._dry_run:
            for a in alerts:
                s = "+" if a["change_pct"] >= 0 else ""
                log.info(f"  [dry-run] {a['name']}({a['code']}) {s}{a['change_pct']:.2f}%  {a['reason']}")
        else:
            send_alert_email(alerts)

    def flush_now(self):
        if self._timer:
            self._timer.cancel()
        self._flush()


# ── 主監控迴圈 ────────────────────────────────────────────────────────────────

class StockMonitor:
    def __init__(self, dry_run: bool = False):
        self._dry_run = dry_run
        self._snapshots: dict[str, StockSnapshot] = {}
        self._batcher = AlertBatcher(MonitorConfig.BATCH_WINDOW_SECONDS, dry_run)
        self._today_alerts_sent: set[str] = set()  # 同一天同一股票只觸發一次
        self._current_date: date | None = None
        self._running = False

        self._load_stocks()

    def _load_stocks(self):
        stocks = get_all_stocks()
        self._snapshots = {
            s["code"]: StockSnapshot(s["code"], s["name"], s.get("industry_name", ""))
            for s in stocks
        }
        log.info(f"載入 {len(self._snapshots)} 支股票")

    def _reset_daily_state(self):
        """每天重置：清空今日警報記錄，重設 alert_count。"""
        self._today_alerts_sent.clear()
        for snap in self._snapshots.values():
            snap.alert_count = 0
        log.info("每日狀態已重置")

    def _check_date_rollover(self):
        today = datetime.now(TZ_TAIPEI).date()
        if self._current_date != today:
            self._current_date = today
            self._reset_daily_state()

    def _poll(self):
        """抓取所有股票最新報價，判斷是否觸發警報。"""
        self._check_date_rollover()
        codes = list(self._snapshots.keys())
        log.debug(f"輪詢 {len(codes)} 支股票...")

        # 分批避免 yfinance 一次請求太多
        BATCH = 50
        for i in range(0, len(codes), BATCH):
            chunk = codes[i: i + BATCH]
            quotes = _fetch_quotes_batch(chunk)
            for code, q in quotes.items():
                snap = self._snapshots.get(code)
                if snap is None:
                    continue
                snap.price = q["price"]
                snap.prev_close = q["prev_close"]
                snap.change_pct = q["change_pct"]
                snap.last_updated = datetime.now(TZ_TAIPEI)
                self._check_alert(snap)
            time.sleep(1)

    def _check_alert(self, snap: StockSnapshot):
        """判斷是否符合警報條件。"""
        pct = snap.change_pct
        alert_key = f"{snap.code}_{self._current_date}"

        # 防止同一天同一股票重複觸發（可依需求改成每次觸發都送）
        if alert_key in self._today_alerts_sent:
            return

        if pct >= MonitorConfig.ALERT_RISE_PCT:
            reason = f"單日漲幅達 +{pct:.1f}%（閾值 +{MonitorConfig.ALERT_RISE_PCT}%）"
        elif pct <= MonitorConfig.ALERT_FALL_PCT:
            reason = f"單日跌幅達 {pct:.1f}%（閾值 {MonitorConfig.ALERT_FALL_PCT}%）"
        else:
            return

        snap.alert_count += 1
        self._today_alerts_sent.add(alert_key)

        s = "+" if pct >= 0 else ""
        log.info(f"⚠  警報觸發：{snap.name}({snap.code}) {s}{pct:.2f}%  {reason}")

        self._batcher.add({
            "code": snap.code,
            "name": snap.name,
            "price": snap.price,
            "prev_close": snap.prev_close,
            "change_pct": pct,
            "reason": reason,
            "triggered_at": snap.last_updated,
        })

    def _send_daily_summary(self):
        """收盤後發送每日摘要。"""
        log.info("發送每日摘要 Email...")
        records = [
            s.to_dict()
            for s in self._snapshots.values()
            if s.price > 0
        ]
        if not records:
            log.warning("無有效報價資料，略過每日摘要。")
            return

        if self._dry_run:
            sorted_r = sorted(records, key=lambda x: x["change_pct"], reverse=True)
            log.info(f"[dry-run] 每日摘要：{len(records)} 支，"
                     f"最大漲幅 {sorted_r[0]['name']} +{sorted_r[0]['change_pct']:.2f}%")
        else:
            send_daily_summary_email(records, top_n=MonitorConfig.SUMMARY_TOP_N)

    def start(self):
        self._running = True

        # 排程：每 N 秒輪詢
        schedule.every(MonitorConfig.POLL_INTERVAL_SECONDS).seconds.do(self._poll)

        # 排程：每日摘要（台灣時間 14:00）
        schedule.every().day.at(MonitorConfig.DAILY_SUMMARY_TIME).do(self._send_daily_summary)

        log.info(
            f"監控啟動 | 股票：{len(self._snapshots)} 支 | "
            f"輪詢間隔：{MonitorConfig.POLL_INTERVAL_SECONDS}s | "
            f"警報閾值：漲 +{MonitorConfig.ALERT_RISE_PCT}% / 跌 {MonitorConfig.ALERT_FALL_PCT}% | "
            f"每日摘要：{MonitorConfig.DAILY_SUMMARY_TIME}"
        )
        if self._dry_run:
            log.info("[dry-run 模式] 警報與摘要只印 log，不實際寄信")

        # 啟動時先執行一次輪詢
        self._poll()

        while self._running:
            schedule.run_pending()
            time.sleep(1)

    def stop(self):
        self._running = False
        self._batcher.flush_now()
        log.info("監控已停止")


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def _send_test_email():
    """發送測試郵件，確認 Gmail SMTP 設定正確。"""
    from datetime import datetime
    log.info("發送測試警報郵件...")
    ok1 = send_alert_email([
        {
            "code": "2330",
            "name": "台積電",
            "price": 850.0,
            "prev_close": 764.0,
            "change_pct": 11.25,
            "reason": "【測試】單日漲幅達 +11.2%",
            "triggered_at": datetime.now(TZ_TAIPEI),
        },
        {
            "code": "2454",
            "name": "聯發科",
            "price": 900.0,
            "prev_close": 970.0,
            "change_pct": -7.22,
            "reason": "【測試】單日跌幅達 -7.2%",
            "triggered_at": datetime.now(TZ_TAIPEI),
        },
    ])

    log.info("發送測試每日摘要郵件...")
    import random
    random.seed(0)
    stocks = get_all_stocks()[:20]
    mock_records = [
        {
            "code": s["code"],
            "name": s["name"],
            "industry_name": s.get("industry_name", ""),
            "price": round(random.uniform(50, 1000), 1),
            "prev_close": round(random.uniform(50, 1000), 1),
            "change_pct": round(random.uniform(-10, 10), 2),
            "alert_count": random.randint(0, 2),
        }
        for s in stocks
    ]
    ok2 = send_daily_summary_email(mock_records, top_n=10)

    if ok1 and ok2:
        log.info("✅ 測試郵件全部寄出成功！")
    else:
        log.error("❌ 部分郵件寄送失敗，請檢查 .env 設定。")


def main():
    parser = argparse.ArgumentParser(description="台股電子類股監控程式")
    parser.add_argument("--test-email", action="store_true", help="發送測試郵件後退出")
    parser.add_argument("--dry-run", action="store_true", help="不實際寄信，只印 log")
    args = parser.parse_args()

    if not EmailConfig.is_configured() and not args.dry_run:
        log.warning(
            "尚未設定 Gmail 憑證！請在 .env 填入：\n"
            "  GMAIL_SENDER=yourname@gmail.com\n"
            "  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx\n"
            "  GMAIL_RECIPIENTS=recipient@example.com\n"
            "或使用 --dry-run 測試監控邏輯。"
        )

    if args.test_email:
        _send_test_email()
        return

    monitor = StockMonitor(dry_run=args.dry_run)

    def _handle_signal(sig, frame):
        log.info(f"收到訊號 {sig}，正在關閉...")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    monitor.start()


if __name__ == "__main__":
    main()
