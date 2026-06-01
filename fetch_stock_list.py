#!/usr/bin/env python3
"""
fetch_stock_list.py

從台灣證交所 (TWSE) 與櫃買中心 (TPEx) API 抓取上市/上櫃電子類股，
篩選產業代碼 24-31，儲存為 stock_list.json。

用法：
    python fetch_stock_list.py             # 抓取並存檔
    python fetch_stock_list.py --dry-run   # 只印出結果，不覆寫檔案
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# ── 目標產業代碼 ──────────────────────────────────────────────────────────────
TARGET_INDUSTRIES: dict[str, str] = {
    "24": "半導體",
    "25": "電腦及週邊",
    "26": "光電",
    "27": "通訊網路",
    "28": "電子零組件",
    "29": "電子設備",
    "30": "資訊服務",
    "31": "其他電子",
}

OUTPUT_PATH = Path(__file__).parent / "stock_list.json"

TWSE_URL = "https://opendata.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (taiwan-stock-predictor/1.0)",
    "Accept": "application/json",
})


# ── TWSE 上市股票 ─────────────────────────────────────────────────────────────

def fetch_twse_stocks() -> list[dict]:
    """
    從證交所 STOCK_DAY_ALL 取得所有上市股票當日行情。
    回傳欄位：code, name, industry_code, industry_name, market
    """
    print("[TWSE] 抓取上市股票清單...")
    try:
        resp = SESSION.get(TWSE_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[TWSE] 抓取失敗：{e}", file=sys.stderr)
        return []

    stocks = []
    for row in data:
        code = str(row.get("Code", "")).strip()
        name = str(row.get("Name", "")).strip()
        # 產業代碼：證交所 STOCK_DAY_ALL 不直接提供產業代碼，
        # 改用股票代號數字範圍推導（台灣上市電子股代號普遍 2300-3699）
        industry_code = _guess_twse_industry(code, name)
        if industry_code in TARGET_INDUSTRIES:
            stocks.append({
                "code": code,
                "name": name,
                "industry_code": industry_code,
                "industry_name": TARGET_INDUSTRIES[industry_code],
                "market": "TWSE",
            })

    print(f"[TWSE] 篩選後電子類股：{len(stocks)} 支")
    return stocks


def _guess_twse_industry(code: str, name: str) -> str:
    """
    STOCK_DAY_ALL 無直接產業欄位，改呼叫證交所分類查詢端點推導。
    若取不到則以代號範圍作粗略對應（僅用於 fallback）。
    """
    # 嘗試從上市公司基本資料 API 取得產業別
    try:
        url = f"https://opendata.twse.com.tw/v1/opendata/t187ap03_L"
        resp = SESSION.get(url, timeout=15)
        if resp.ok:
            for item in resp.json():
                if str(item.get("公司代號", "")).strip() == code:
                    raw = str(item.get("產業別", "")).strip()
                    return _normalize_industry_code(raw)
    except Exception:
        pass

    # Fallback：代號範圍對應（台灣電子股慣例）
    RANGE_MAP = [
        ((2300, 2329), "24"),  # 半導體
        ((2330, 2399), "24"),  # 半導體（台積電等）
        ((2400, 2429), "25"),  # 電腦及週邊
        ((2430, 2459), "24"),  # 半導體
        ((2460, 2499), "28"),  # 電子零組件
        ((2500, 2549), "26"),  # 光電
        ((2550, 2599), "27"),  # 通訊網路
        ((2600, 2649), "29"),  # 電子設備
        ((2650, 2699), "30"),  # 資訊服務
        ((2700, 2799), "31"),  # 其他電子
        ((3000, 3099), "24"),  # 半導體
        ((3100, 3199), "25"),  # 電腦及週邊
        ((3200, 3299), "28"),  # 電子零組件
        ((3300, 3399), "27"),  # 通訊網路
        ((3400, 3499), "26"),  # 光電
        ((3500, 3599), "30"),  # 資訊服務
        ((3600, 3699), "31"),  # 其他電子
        ((6200, 6299), "30"),  # 資訊服務
        ((6400, 6499), "24"),  # 半導體
        ((8000, 8099), "30"),  # 資訊服務
    ]
    try:
        num = int(code)
        for (lo, hi), industry in RANGE_MAP:
            if lo <= num <= hi:
                return industry
    except ValueError:
        pass
    return ""


def _normalize_industry_code(raw: str) -> str:
    """將證交所中文產業別對應到代碼。"""
    MAPPING = {
        "半導體業": "24",
        "電腦及週邊設備業": "25",
        "光電業": "26",
        "通信網路業": "27",
        "通訊網路業": "27",
        "電子零組件業": "28",
        "電子通路業": "29",
        "電子設備業": "29",
        "資訊服務業": "30",
        "其他電子業": "31",
    }
    for key, code in MAPPING.items():
        if key in raw:
            return code
    return ""


# ── TPEx 上櫃股票 ─────────────────────────────────────────────────────────────

def fetch_tpex_stocks() -> list[dict]:
    """
    從櫃買中心 tpex_mainboard_quotes 取得上櫃股票行情，
    篩選電子產業代碼。
    """
    print("[TPEx] 抓取上櫃股票清單...")
    try:
        resp = SESSION.get(TPEX_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[TPEx] 抓取失敗：{e}", file=sys.stderr)
        return []

    stocks = []
    for row in data:
        code = str(row.get("SecuritiesCompanyCode", row.get("代號", ""))).strip()
        name = str(row.get("CompanyName", row.get("名稱", ""))).strip()
        # TPEx API 回傳的產業分類欄位名稱
        industry_raw = str(
            row.get("IndustryCode",
            row.get("industryCode",
            row.get("industry_code",
            row.get("產業別", ""))))
        ).strip()

        industry_code = _tpex_industry_code(industry_raw, code)
        if industry_code in TARGET_INDUSTRIES:
            stocks.append({
                "code": code,
                "name": name,
                "industry_code": industry_code,
                "industry_name": TARGET_INDUSTRIES[industry_code],
                "market": "TPEx",
            })

    print(f"[TPEx] 篩選後電子類股：{len(stocks)} 支")
    return stocks


def _tpex_industry_code(raw: str, code: str) -> str:
    """
    解析 TPEx 回傳的產業欄位，支援數字代碼或中文名稱兩種格式。
    """
    # 直接是目標代碼數字
    if raw in TARGET_INDUSTRIES:
        return raw

    # 中文名稱對應
    MAPPING = {
        "半導體": "24",
        "電腦及週邊": "25",
        "電腦週邊": "25",
        "光電": "26",
        "通訊網路": "27",
        "通信網路": "27",
        "電子零組件": "28",
        "電子設備": "29",
        "電子通路": "29",
        "資訊服務": "30",
        "其他電子": "31",
    }
    for key, c in MAPPING.items():
        if key in raw:
            return c

    # Fallback：代號數字範圍（上櫃電子股常見範圍）
    try:
        num = int(code)
        if 4100 <= num <= 4999:
            return "31"
        if 5000 <= num <= 5299:
            return "30"
        if 6600 <= num <= 6799:
            return "24"
    except ValueError:
        pass

    return ""


# ── 補充：證交所產業分類 API（更精確） ────────────────────────────────────────

def fetch_twse_industry_list() -> list[dict]:
    """
    呼叫證交所上市公司基本資料取得準確的產業代碼對應，
    作為 STOCK_DAY_ALL 的補充資料來源。
    """
    print("[TWSE] 抓取產業分類資料...")
    url = "https://opendata.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[TWSE] 產業分類資料抓取失敗：{e}", file=sys.stderr)
        return []

    stocks = []
    for row in data:
        code = str(row.get("公司代號", "")).strip()
        name = str(row.get("公司簡稱", row.get("公司名稱", ""))).strip()
        industry_raw = str(row.get("產業別", "")).strip()
        industry_code = _normalize_industry_code(industry_raw)
        if industry_code in TARGET_INDUSTRIES and code:
            stocks.append({
                "code": code,
                "name": name,
                "industry_code": industry_code,
                "industry_name": TARGET_INDUSTRIES[industry_code],
                "market": "TWSE",
            })

    print(f"[TWSE] 產業分類 API 電子類股：{len(stocks)} 支")
    return stocks


# ── 合併去重 ──────────────────────────────────────────────────────────────────

def merge_and_deduplicate(sources: list[list[dict]]) -> list[dict]:
    """合併多個來源，以股票代號去重（保留資訊最完整的那筆）。"""
    seen: dict[str, dict] = {}
    for source in sources:
        for stock in source:
            code = stock["code"]
            if code not in seen:
                seen[code] = stock
            else:
                # 若已有資料，只有當新資料有 industry_code 而舊資料沒有時才覆寫
                if not seen[code].get("industry_code") and stock.get("industry_code"):
                    seen[code] = stock

    # 依代號排序
    result = sorted(seen.values(), key=lambda x: x["code"])
    return result


# ── 主程式 ────────────────────────────────────────────────────────────────────

def build_stock_list(dry_run: bool = False) -> list[dict]:
    """執行完整抓取流程，回傳股票清單並寫入 stock_list.json。"""
    print("=" * 60)
    print("台灣電子類股清單抓取程式")
    print(f"目標產業：{', '.join(f'{k}({v})' for k,v in TARGET_INDUSTRIES.items())}")
    print("=" * 60)

    # 來源 1：證交所產業分類 API（最精確）
    twse_industry = fetch_twse_industry_list()
    time.sleep(0.5)

    # 來源 2：證交所當日行情（涵蓋最新上市）
    twse_daily = fetch_twse_stocks()
    time.sleep(0.5)

    # 來源 3：櫃買中心上櫃行情
    tpex_daily = fetch_tpex_stocks()

    # 合併，優先以產業分類 API 為準
    all_stocks = merge_and_deduplicate([twse_industry, twse_daily, tpex_daily])

    # 統計
    by_industry: dict[str, list] = {}
    for s in all_stocks:
        by_industry.setdefault(s["industry_code"], []).append(s)

    print("\n── 篩選結果 ──")
    for code, name in TARGET_INDUSTRIES.items():
        count = len(by_industry.get(code, []))
        print(f"  {code} {name}：{count} 支")
    print(f"  合計：{len(all_stocks)} 支")

    if not all_stocks:
        print("\n警告：未抓到任何股票，請確認網路連線。", file=sys.stderr)

    payload = {
        "generated_at": _now_str(),
        "total": len(all_stocks),
        "industries": TARGET_INDUSTRIES,
        "stocks": all_stocks,
    }

    if dry_run:
        print("\n[dry-run] 不寫入檔案。")
    else:
        OUTPUT_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n已寫入：{OUTPUT_PATH}  ({len(all_stocks)} 支股票)")

    return all_stocks


def _now_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取台灣電子類上市/上櫃股票清單")
    parser.add_argument("--dry-run", action="store_true", help="只印出結果，不寫入檔案")
    args = parser.parse_args()
    build_stock_list(dry_run=args.dry_run)
