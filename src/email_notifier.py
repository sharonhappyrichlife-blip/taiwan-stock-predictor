"""
email_notifier.py

Gmail SMTP 電子郵件通知模組。
提供警報郵件（多股合併一封）與每日摘要郵件。
"""

import smtplib
import textwrap
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

try:
    from .config import EmailConfig
except ImportError:
    from config import EmailConfig

TZ_TAIPEI = ZoneInfo("Asia/Taipei")


# ── 時間工具 ──────────────────────────────────────────────────────────────────

def _now_taipei() -> datetime:
    return datetime.now(TZ_TAIPEI)


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── SMTP 發送核心 ─────────────────────────────────────────────────────────────

def _send(subject: str, html_body: str, text_body: str) -> bool:
    """
    透過 Gmail SMTP TLS 發送郵件。
    回傳 True 表示成功，False 表示失敗（錯誤已印出）。
    """
    if not EmailConfig.is_configured():
        print(
            "[email] 尚未設定 Gmail 憑證，請在 .env 填入 GMAIL_SENDER / "
            "GMAIL_APP_PASSWORD / GMAIL_RECIPIENTS。"
        )
        return False

    recipients = EmailConfig.recipient_list()
    if not recipients:
        print("[email] 收件者清單為空，略過寄送。")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EmailConfig.SENDER
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(EmailConfig.SMTP_HOST, EmailConfig.SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(EmailConfig.SENDER, EmailConfig.APP_PASSWORD)
            server.sendmail(EmailConfig.SENDER, recipients, msg.as_bytes())
        print(f"[email] 已寄出：{subject}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(
            "[email] Gmail 認證失敗。請確認：\n"
            "  1. GMAIL_SENDER 是完整 Gmail 地址\n"
            "  2. GMAIL_APP_PASSWORD 是「應用程式密碼」(16 碼)，非帳號密碼\n"
            "  3. Gmail 帳號已啟用「兩步驟驗證」"
        )
    except Exception as e:
        print(f"[email] 寄送失敗：{e}")
    return False


# ── 警報郵件 ──────────────────────────────────────────────────────────────────

def send_alert_email(alerts: list[dict]) -> bool:
    """
    發送股票警報郵件，多支股票合併成一封。

    alerts 格式：
    [
      {
        "code": "2330",
        "name": "台積電",
        "price": 850.0,
        "change_pct": 11.2,    # 正數=漲，負數=跌
        "prev_close": 764.0,
        "reason": "單日漲幅超過 +5.0%",
        "triggered_at": datetime,   # 可選
      },
      ...
    ]
    """
    if not alerts:
        return False

    now = _now_taipei()

    # ── 主旨：取最大絕對漲跌幅的股票 ────────────────────────────────────────
    top = max(alerts, key=lambda a: abs(a.get("change_pct", 0)))
    direction = "漲幅" if top["change_pct"] >= 0 else "跌幅"
    sign = "+" if top["change_pct"] >= 0 else ""
    if len(alerts) == 1:
        subject = (
            f"【台股警報】{top['name']}({top['code']}) "
            f"單日{direction} {sign}{top['change_pct']:.1f}%"
        )
    else:
        subject = (
            f"【台股警報】{len(alerts)} 支股票觸發條件 — "
            f"最大{direction} {top['name']}({top['code']}) {sign}{top['change_pct']:.1f}%"
        )

    # ── 純文字版本 ────────────────────────────────────────────────────────────
    text_lines = [
        "台股警報通知",
        f"發送時間：{_fmt_time(now)}",
        "=" * 50,
    ]
    for a in sorted(alerts, key=lambda x: abs(x.get("change_pct", 0)), reverse=True):
        s = "+" if a["change_pct"] >= 0 else ""
        text_lines += [
            f"股票：{a['name']} ({a['code']})",
            f"現價：{a['price']:.2f}  漲跌幅：{s}{a['change_pct']:.2f}%",
            f"前日收盤：{a.get('prev_close', 'N/A')}",
            f"觸發原因：{a.get('reason', '')}",
            f"觸發時間：{_fmt_time(a['triggered_at']) if a.get('triggered_at') else _fmt_time(now)}",
            "-" * 40,
        ]
    text_body = "\n".join(text_lines)

    # ── HTML 版本 ─────────────────────────────────────────────────────────────
    rows_html = ""
    for a in sorted(alerts, key=lambda x: abs(x.get("change_pct", 0)), reverse=True):
        s = "+" if a["change_pct"] >= 0 else ""
        color = "#d32f2f" if a["change_pct"] < 0 else "#1b5e20"
        bg = "#ffebee" if a["change_pct"] < 0 else "#e8f5e9"
        t = _fmt_time(a["triggered_at"]) if a.get("triggered_at") else _fmt_time(now)
        rows_html += f"""
        <tr style="background:{bg}">
          <td style="padding:10px;font-weight:bold">{a['name']}<br>
              <span style="color:#555;font-size:12px">{a['code']}</span></td>
          <td style="padding:10px;text-align:right;font-size:20px;font-weight:bold">
              {a['price']:.2f}</td>
          <td style="padding:10px;text-align:right;color:{color};font-size:18px;font-weight:bold">
              {s}{a['change_pct']:.2f}%</td>
          <td style="padding:10px;color:#555">{a.get('reason','')}</td>
          <td style="padding:10px;color:#777;font-size:12px">{t}</td>
        </tr>"""

    html_body = _wrap_html(
        title="⚠️ 台股警報通知",
        subtitle=f"發送時間：{_fmt_time(now)}",
        content=f"""
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border-collapse:collapse;font-family:sans-serif;font-size:14px">
          <thead>
            <tr style="background:#37474f;color:#fff">
              <th style="padding:10px;text-align:left">股票</th>
              <th style="padding:10px;text-align:right">現價</th>
              <th style="padding:10px;text-align:right">漲跌幅</th>
              <th style="padding:10px;text-align:left">觸發原因</th>
              <th style="padding:10px;text-align:left">觸發時間</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>""",
    )

    return _send(subject, html_body, text_body)


# ── 每日摘要郵件 ──────────────────────────────────────────────────────────────

def send_daily_summary_email(daily_records: list[dict], top_n: int = 10) -> bool:
    """
    發送每日收盤後摘要郵件。

    daily_records 格式（當天監控的所有股票）：
    [
      {
        "code": "2330",
        "name": "台積電",
        "price": 850.0,
        "change_pct": 3.5,
        "prev_close": 821.0,
        "industry_name": "半導體",
        "alert_count": 1,      # 當天觸發警報次數
      },
      ...
    ]
    """
    if not daily_records:
        return False

    now = _now_taipei()
    date_str = now.strftime("%Y/%m/%d")
    subject = f"【台股每日摘要】{date_str} 電子類股漲跌排行"

    # 排序
    sorted_by_chg = sorted(daily_records, key=lambda x: x.get("change_pct", 0), reverse=True)
    top_gainers = sorted_by_chg[:top_n]
    top_losers = sorted_by_chg[-top_n:][::-1]
    alert_stocks = [r for r in daily_records if r.get("alert_count", 0) > 0]

    total = len(daily_records)
    up_count = sum(1 for r in daily_records if r.get("change_pct", 0) > 0)
    down_count = sum(1 for r in daily_records if r.get("change_pct", 0) < 0)
    flat_count = total - up_count - down_count
    avg_chg = sum(r.get("change_pct", 0) for r in daily_records) / max(total, 1)

    # ── 純文字 ────────────────────────────────────────────────────────────────
    text_lines = [
        f"台股每日摘要 {date_str}",
        f"監控股票：{total} 支  上漲：{up_count}  下跌：{down_count}  平盤：{flat_count}",
        f"平均漲跌幅：{avg_chg:+.2f}%",
        "=" * 50,
        f"\n▲ 漲幅前 {top_n} 名",
    ]
    for i, r in enumerate(top_gainers, 1):
        text_lines.append(f"  {i:2}. {r['name']}({r['code']})  {r['price']:.2f}  +{r['change_pct']:.2f}%")
    text_lines.append(f"\n▼ 跌幅前 {top_n} 名")
    for i, r in enumerate(top_losers, 1):
        text_lines.append(f"  {i:2}. {r['name']}({r['code']})  {r['price']:.2f}  {r['change_pct']:.2f}%")
    if alert_stocks:
        text_lines.append(f"\n⚠ 今日觸發警報 ({len(alert_stocks)} 支)")
        for r in alert_stocks:
            text_lines.append(f"  {r['name']}({r['code']})  警報 {r['alert_count']} 次")
    text_body = "\n".join(text_lines)

    # ── HTML ──────────────────────────────────────────────────────────────────
    def _rank_rows(stocks: list[dict], positive: bool) -> str:
        html = ""
        for i, r in enumerate(stocks, 1):
            pct = r.get("change_pct", 0)
            color = "#d32f2f" if pct < 0 else "#1b5e20"
            bg = "#fff" if i % 2 == 0 else "#fafafa"
            s = "+" if pct >= 0 else ""
            html += f"""
            <tr style="background:{bg}">
              <td style="padding:8px;text-align:center;color:#777">{i}</td>
              <td style="padding:8px">{r['name']}<br>
                  <span style="color:#999;font-size:11px">{r['code']} · {r.get('industry_name','')}</span></td>
              <td style="padding:8px;text-align:right">{r['price']:.2f}</td>
              <td style="padding:8px;text-align:right;color:{color};font-weight:bold">
                  {s}{pct:.2f}%</td>
            </tr>"""
        return html

    def _table(title: str, rows_html: str, header_color: str) -> str:
        return f"""
        <h3 style="color:{header_color};margin-top:24px">{title}</h3>
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border-collapse:collapse;font-family:sans-serif;font-size:14px">
          <thead>
            <tr style="background:{header_color};color:#fff">
              <th style="padding:8px;width:36px">#</th>
              <th style="padding:8px;text-align:left">股票</th>
              <th style="padding:8px;text-align:right">現價</th>
              <th style="padding:8px;text-align:right">漲跌幅</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>"""

    alert_section = ""
    if alert_stocks:
        alert_rows = "".join(
            f"<li>{r['name']}({r['code']}) — 觸發 {r['alert_count']} 次</li>"
            for r in alert_stocks
        )
        alert_section = f"""
        <h3 style="color:#e65100;margin-top:24px">⚠️ 今日觸發警報（{len(alert_stocks)} 支）</h3>
        <ul style="font-family:sans-serif;font-size:14px">{alert_rows}</ul>"""

    content = f"""
    <div style="font-family:sans-serif;font-size:14px;background:#f5f5f5;
                padding:12px 16px;border-radius:6px;margin-bottom:16px">
      監控股票：<b>{total}</b> 支 ·
      上漲 <b style="color:#1b5e20">{up_count}</b> ·
      下跌 <b style="color:#d32f2f">{down_count}</b> ·
      平盤 {flat_count} ·
      平均漲跌幅 <b>{avg_chg:+.2f}%</b>
    </div>
    {_table(f"▲ 漲幅前 {top_n} 名", _rank_rows(top_gainers, True), "#2e7d32")}
    {_table(f"▼ 跌幅前 {top_n} 名", _rank_rows(top_losers, False), "#c62828")}
    {alert_section}"""

    html_body = _wrap_html(
        title=f"📊 台股每日摘要 {date_str}",
        subtitle=f"發送時間：{_fmt_time(now)}",
        content=content,
    )
    return _send(subject, html_body, text_body)


# ── HTML 版型 ─────────────────────────────────────────────────────────────────

def _wrap_html(title: str, subtitle: str, content: str) -> str:
    return textwrap.dedent(f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#ececec">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:24px 0">
          <table width="640" cellpadding="0" cellspacing="0"
                 style="background:#fff;border-radius:8px;
                        box-shadow:0 2px 8px rgba(0,0,0,.12)">
            <tr><td style="background:#1a237e;border-radius:8px 8px 0 0;
                           padding:20px 24px">
              <h2 style="margin:0;color:#fff;font-family:sans-serif">{title}</h2>
              <p style="margin:4px 0 0;color:#9fa8da;font-family:sans-serif;
                        font-size:13px">{subtitle}</p>
            </td></tr>
            <tr><td style="padding:20px 24px">{content}</td></tr>
            <tr><td style="padding:12px 24px;border-top:1px solid #eee;
                           font-family:sans-serif;font-size:11px;color:#9e9e9e">
              台股情緒分析監控系統 · 此為自動發送郵件，請勿直接回覆
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body></html>
    """).strip()
