import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from data_fetcher import fetch_stock_data, TAIWAN_STOCKS, generate_mock_sentiment
from technical_indicators import add_all_indicators, get_signal_summary
from granger_analysis import (
    sentiment_stock_granger, cross_correlation_analysis,
    sentiment_lead_lag_analysis, rolling_granger,
    sentiment_predictive_score,
)
from sentiment_analyzer import generate_sample_news, analyze_news_batch, aggregate_daily_sentiment, sentiment_momentum

st.set_page_config(
    page_title="台股情緒分析儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%);
    border-radius: 12px; padding: 16px; margin: 6px 0;
    border-left: 4px solid #4fc3f7;
}
.signal-bull { color: #26a69a; font-weight: bold; }
.signal-bear { color: #ef5350; font-weight: bold; }
.signal-neutral { color: #ffa726; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ 設定")
stock_options = {f"{code} {name}": code for code, name in TAIWAN_STOCKS.items()}
selected_display = st.sidebar.selectbox("選擇股票", list(stock_options.keys()), index=0)
selected_stock = stock_options[selected_display]
stock_name = TAIWAN_STOCKS[selected_stock]

period = st.sidebar.selectbox("資料期間", ["3mo", "6mo", "1y", "2y"], index=2)
max_granger_lag = st.sidebar.slider("格蘭傑最大落後期數", 1, 10, 5)

st.sidebar.markdown("---")
st.sidebar.markdown("### 顯示設定")
show_volume = st.sidebar.checkbox("顯示成交量", True)
show_bb = st.sidebar.checkbox("顯示布林通道", True)
show_ma = st.sidebar.checkbox("顯示均線", True)


@st.cache_data(ttl=300)
def load_data(symbol: str, period: str):
    df = fetch_stock_data(symbol, period)
    if df.empty:
        return pd.DataFrame()
    return add_all_indicators(df)


@st.cache_data(ttl=300)
def load_sentiment(stock_name: str, dates_key: str):
    dates = pd.date_range(end=pd.Timestamp.today(), periods=252, freq="B")
    news = generate_sample_news(stock_name, dates)
    news_df = analyze_news_batch(news)
    daily = aggregate_daily_sentiment(news_df)
    return daily, sentiment_momentum(daily)


with st.spinner(f"載入 {stock_name} 資料中..."):
    df = load_data(selected_stock, period)

st.title("📈 台股情緒分析儀表板")
st.markdown(f"### {selected_stock} {stock_name} | {period.upper()} 分析")

if df.empty:
    st.error("無法取得資料，請確認網路連線或稍後再試。")
    st.stop()

# ── KPI Row ───────────────────────────────────────────────────────────────────
latest = df.iloc[-1]
prev = df.iloc[-2]
price_chg = (latest["close"] - prev["close"]) / prev["close"] * 100
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("收盤價", f"${latest['close']:.2f}", f"{price_chg:+.2f}%")
c2.metric("RSI(14)", f"{latest['rsi']:.1f}", delta_color="off")
c3.metric("MACD", f"{latest['macd']:.3f}", f"{latest['macd_hist']:+.3f}")
c4.metric("成交量", f"{latest['volume']/1e6:.1f}M", f"{(latest['vol_ratio']-1)*100:+.1f}%")
c5.metric("ATR(14)", f"{latest['atr']:.2f}", delta_color="off")

st.markdown("---")
tab1, tab2, tab3, tab4 = st.tabs(["📊 技術分析", "🧠 情緒分析", "🔗 格蘭傑因果", "📋 訊號摘要"])

# ── Tab 1: Technical Analysis ─────────────────────────────────────────────────
with tab1:
    rows = 4 if show_volume else 3
    row_heights = [0.5, 0.2, 0.15, 0.15] if show_volume else [0.55, 0.25, 0.2]
    subplot_titles = ["價格", "MACD", "RSI"] + (["成交量"] if show_volume else [])

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        vertical_spacing=0.04, row_heights=row_heights,
                        subplot_titles=subplot_titles)

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K線", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    if show_ma:
        for ma, color in [("ma5", "#ffd54f"), ("ma20", "#42a5f5"), ("ma60", "#ef9a9a")]:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], name=ma.upper(),
                                     line=dict(color=color, width=1.2)), row=1, col=1)

    if show_bb:
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB上軌",
                                 line=dict(color="#b0bec5", width=1, dash="dot"), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB下軌",
                                 line=dict(color="#b0bec5", width=1, dash="dot"),
                                 fill="tonexty", fillcolor="rgba(176,190,197,0.1)", showlegend=False), row=1, col=1)

    hist_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in df["macd_hist"]]
    fig.add_trace(go.Bar(x=df.index, y=df["macd_hist"], marker_color=hist_colors, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd"], name="MACD", line=dict(color="#42a5f5", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd_signal"], name="Signal", line=dict(color="#ffa726", width=1.5)), row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI", line=dict(color="#ce93d8", width=1.5)), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", row=3, col=1)

    if show_volume:
        vol_colors = ["#26a69a" if df["close"].iloc[i] >= df["open"].iloc[i] else "#ef5350" for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=vol_colors, showlegend=False), row=4, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["vol_ma20"], name="量均線",
                                 line=dict(color="#ffd54f", width=1), showlegend=False), row=4, col=1)

    fig.update_layout(height=750, template="plotly_dark", xaxis_rangeslider_visible=False,
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig_bb = px.line(df, x=df.index, y="bb_width", title="布林通道寬度 (波動率)", template="plotly_dark")
        fig_bb.update_layout(height=280, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
        st.plotly_chart(fig_bb, use_container_width=True)
    with col2:
        fig_sto = go.Figure()
        fig_sto.add_trace(go.Scatter(x=df.index, y=df["stoch_k"], name="%K", line=dict(color="#42a5f5")))
        fig_sto.add_trace(go.Scatter(x=df.index, y=df["stoch_d"], name="%D", line=dict(color="#ffa726")))
        fig_sto.add_hline(y=80, line_dash="dash", line_color="#ef5350")
        fig_sto.add_hline(y=20, line_dash="dash", line_color="#26a69a")
        fig_sto.update_layout(title="隨機震盪指標 (Stochastic)", height=280, template="plotly_dark",
                               paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
        st.plotly_chart(fig_sto, use_container_width=True)

# ── Tab 2: Sentiment ──────────────────────────────────────────────────────────
with tab2:
    dates_key = str(df.index[0]) + str(df.index[-1])
    with st.spinner("分析情緒中..."):
        daily_sentiment, sent_mom = load_sentiment(stock_name, dates_key)

    aligned = pd.concat([df["close"], df["returns"], daily_sentiment.rename("sentiment")], axis=1).dropna()
    aligned["sent_momentum"] = sentiment_momentum(aligned["sentiment"])

    col1, col2 = st.columns([2, 1])
    with col1:
        fig_s = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                               subplot_titles=["收盤價 vs 情緒指數", "情緒動能 (5日均線)"],
                               row_heights=[0.6, 0.4])
        fig_s.add_trace(go.Scatter(x=aligned.index, y=aligned["close"], name="收盤價",
                                   line=dict(color="#42a5f5")), row=1, col=1)
        sent_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in aligned["sentiment"]]
        fig_s.add_trace(go.Bar(x=aligned.index, y=aligned["sentiment"], marker_color=sent_colors,
                                showlegend=False), row=1, col=1)
        fig_s.add_trace(go.Scatter(x=aligned.index, y=aligned["sent_momentum"], name="情緒動能",
                                   line=dict(color="#ffd54f", width=2)), row=2, col=1)
        fig_s.add_hline(y=0, line_dash="dash", line_color="#78909c", row=2, col=1)
        fig_s.update_layout(height=520, template="plotly_dark", paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
        st.plotly_chart(fig_s, use_container_width=True)

    with col2:
        st.markdown("#### 情緒統計")
        avg_s = aligned["sentiment"].mean()
        st.metric("平均情緒", f"{avg_s:.3f}")
        st.metric("情緒標準差", f"{aligned['sentiment'].std():.3f}")
        st.metric("正向天數", f"{(aligned['sentiment'] > 0.1).sum()}")
        st.metric("負向天數", f"{(aligned['sentiment'] < -0.1).sum()}")
        fig_dist = px.histogram(aligned, x="sentiment", nbins=30, title="情緒分佈",
                                 template="plotly_dark", color_discrete_sequence=["#42a5f5"])
        fig_dist.update_layout(height=280, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117", showlegend=False)
        st.plotly_chart(fig_dist, use_container_width=True)

    st.markdown("#### 情緒 vs 次日報酬率")
    scatter_df = aligned.copy()
    scatter_df["next_return"] = scatter_df["returns"].shift(-1)
    scatter_df = scatter_df.dropna()
    fig_sc = px.scatter(scatter_df, x="sentiment", y="next_return", trendline="ols",
                         template="plotly_dark", title="情緒分數 vs 次日報酬率（含趨勢線）",
                         labels={"sentiment": "情緒分數", "next_return": "次日報酬率"},
                         color_discrete_sequence=["#42a5f5"])
    fig_sc.update_layout(height=350, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
    st.plotly_chart(fig_sc, use_container_width=True)

# ── Tab 3: Granger Causality ──────────────────────────────────────────────────
with tab3:
    st.markdown("## 🔗 格蘭傑因果分析 (Granger Causality)")
    st.markdown("""
格蘭傑因果性測試用於確定一個時間序列是否能**統計上預測**另一個時間序列。
本模組包含：**雙向因果檢定**、**情緒領先/落後分解**、**滾動視窗時變因果**、**預測力評分**。
    """)

    dates_key = str(df.index[0]) + str(df.index[-1])
    daily_sentiment, _ = load_sentiment(stock_name, dates_key)
    aligned = pd.concat([df["returns"], daily_sentiment.rename("sentiment")], axis=1).dropna()

    if len(aligned) < 30:
        st.warning("資料點不足，無法進行格蘭傑分析。")
    else:
        subtab1, subtab2, subtab3, subtab4 = st.tabs(
            ["📊 雙向因果", "⏱ 領先/落後分析", "🔄 滾動視窗", "🎯 預測力評分"]
        )

        # ── Sub-tab 1: Bidirectional Granger ────────────────────────────────
        with subtab1:
            with st.spinner("執行格蘭傑因果分析..."):
                granger_result = sentiment_stock_granger(
                    aligned["sentiment"], aligned["returns"], max_lag=max_granger_lag
                )
            s2r = granger_result["sentiment_causes_return"]
            r2s = granger_result["return_causes_sentiment"]

            col1, col2 = st.columns(2)
            for col, res, title in [(col1, s2r, "情緒 → 報酬率"), (col2, r2s, "報酬率 → 情緒")]:
                with col:
                    st.markdown(f"### {title}")
                    if not res.get("error"):
                        sig = res["granger_causes"]
                        badge = "✅ 顯著" if sig else "❌ 不顯著"
                        st.markdown(f"**結果：{badge}**")
                        st.markdown(f"最佳落後期數：**{res['best_lag']}**")
                        st.markdown(f"P 值：**{res['best_p_value']:.4f}**")
                        st.markdown(f"F 統計量：**{res.get('best_f_stat', 0):.3f}**")
                        st.markdown(f"顯著期數：**{res.get('n_significant_lags', 0)} / {max_granger_lag}**")
                    else:
                        st.error(res["error"])

            st.markdown("---")
            pval_data = []
            if not s2r.get("error") and "results" in s2r:
                pval_data += [{"lag": k, "p_value": v["p_value"], "F統計量": v["f_stat"], "type": "情緒→報酬"}
                               for k, v in s2r["results"].items()]
            if not r2s.get("error") and "results" in r2s:
                pval_data += [{"lag": k, "p_value": v["p_value"], "F統計量": v["f_stat"], "type": "報酬→情緒"}
                               for k, v in r2s["results"].items()]
            if pval_data:
                c1, c2 = st.columns(2)
                with c1:
                    fig_pv = px.line(pd.DataFrame(pval_data), x="lag", y="p_value", color="type",
                                      title="P 值 vs 落後期數", template="plotly_dark",
                                      color_discrete_map={"情緒→報酬": "#42a5f5", "報酬→情緒": "#ffa726"})
                    fig_pv.add_hline(y=0.05, line_dash="dash", line_color="#ef5350", annotation_text="p=0.05")
                    fig_pv.update_layout(height=320, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_pv, use_container_width=True)
                with c2:
                    fig_f = px.bar(pd.DataFrame(pval_data), x="lag", y="F統計量", color="type", barmode="group",
                                    title="F 統計量 vs 落後期數", template="plotly_dark",
                                    color_discrete_map={"情緒→報酬": "#42a5f5", "報酬→情緒": "#ffa726"})
                    fig_f.update_layout(height=320, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_f, use_container_width=True)

            with st.expander("📋 平穩性檢定 (ADF + KPSS)"):
                for key, info in granger_result.get("stationarity", {}).items():
                    label = "情緒序列" if key == "sentiment" else "報酬率序列"
                    adf_ok = "✅" if info.get("is_stationary") else "⚠️"
                    conclusion_zh = {"stationary": "平穩", "non_stationary": "非平穩", "uncertain": "不確定"}.get(
                        info.get("conclusion", ""), "—"
                    )
                    st.markdown(
                        f"**{label}** {adf_ok} {conclusion_zh} | "
                        f"ADF p={info.get('adf_p', info.get('p_value', 1)):.4f} | "
                        f"KPSS p={info.get('kpss_p', float('nan')):.4f}"
                    )

        # ── Sub-tab 2: Lead / Lag analysis ─────────────────────────────────
        with subtab2:
            st.markdown("### ⏱ 情緒領先/落後股價分析")
            st.markdown("""
- **正落後 (k > 0)**：情緒在 k 期前是否能預測當期報酬（情緒**領先**）
- **負落後 (k < 0)**：當期報酬是否受 k 期前股價影響（情緒**落後**）
            """)

            with st.spinner("計算領先落後結構..."):
                ll = sentiment_lead_lag_analysis(
                    aligned["sentiment"], aligned["returns"], max_lag=max_granger_lag
                )

            summary = ll["summary"]
            rel_color = {
                "sentiment_leads": "#26a69a",
                "price_leads": "#ef5350",
                "bidirectional": "#ffd54f",
                "none": "#78909c",
            }.get(summary["relationship"], "#78909c")

            st.markdown(
                f"<div style='background:{rel_color}22; border-left:4px solid {rel_color}; "
                f"padding:12px; border-radius:8px; margin-bottom:12px'>"
                f"<b>關係類型：{summary['relationship_zh']}</b><br>"
                f"{summary['interpretation']}</div>",
                unsafe_allow_html=True,
            )

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("最佳領先期", f"{summary['optimal_lead_k'] or '—'} 日")
            mc2.metric("領先最低 P 值", f"{summary['best_lead_p_value']:.4f}")
            mc3.metric("最佳落後期", f"{summary['optimal_lag_k'] or '—'} 日")
            mc4.metric("落後最低 P 值", f"{summary['best_lag_p_value']:.4f}")

            st.markdown("---")

            # Cross-correlation heatmap-style bar chart
            cc_df = ll["cross_corr_df"]
            fig_cc = go.Figure()
            colors = ["#26a69a" if r > 0 else "#ef5350" for r in cc_df["correlation"]]
            fig_cc.add_trace(go.Bar(
                x=cc_df["lag"], y=cc_df["correlation"],
                marker_color=colors,
                text=[f"p={p:.3f}" for p in cc_df["p_value"]],
                textposition="outside",
                name="相關係數",
            ))
            fig_cc.add_hline(y=0, line_color="#ffffff", line_width=0.8)
            # Mark significant bars
            sig_df = cc_df[cc_df["significant"]]
            if not sig_df.empty:
                fig_cc.add_trace(go.Scatter(
                    x=sig_df["lag"], y=sig_df["correlation"] * 0,
                    mode="markers", marker=dict(symbol="star", size=14, color="#ffd54f"),
                    name="顯著 (p<0.05)",
                ))
            fig_cc.update_layout(
                title="互相關係數（負=情緒落後，正=情緒領先，★=顯著）",
                xaxis_title="落後期數 (交易日)",
                yaxis_title="Pearson 相關係數",
                template="plotly_dark", height=380,
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            )
            st.plotly_chart(fig_cc, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                lead_df = ll["lead_df"]
                if not lead_df.empty:
                    fig_lead = px.bar(lead_df, x="lead_k", y="p_value",
                                       title="情緒領先 k 期 → 報酬率 (Granger P 值)",
                                       template="plotly_dark",
                                       color="significant",
                                       color_discrete_map={True: "#26a69a", False: "#546e7a"},
                                       labels={"lead_k": "領先期數 k", "p_value": "P 值"})
                    fig_lead.add_hline(y=0.05, line_dash="dash", line_color="#ef5350")
                    fig_lead.update_layout(height=300, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_lead, use_container_width=True)
            with c2:
                lag_df = ll["lag_df"]
                if not lag_df.empty:
                    fig_lag = px.bar(lag_df, x="lag_k", y="p_value",
                                      title="報酬率領先 k 期 → 情緒 (Granger P 值)",
                                      template="plotly_dark",
                                      color="significant",
                                      color_discrete_map={True: "#ffa726", False: "#546e7a"},
                                      labels={"lag_k": "落後期數 k", "p_value": "P 值"})
                    fig_lag.add_hline(y=0.05, line_dash="dash", line_color="#ef5350")
                    fig_lag.update_layout(height=300, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_lag, use_container_width=True)

        # ── Sub-tab 3: Rolling Granger ──────────────────────────────────────
        with subtab3:
            st.markdown("### 🔄 滾動視窗格蘭傑因果（時變因果）")
            st.markdown("以固定視窗滾動計算格蘭傑因果 P 值，偵測因果關係的**結構性轉變**。")

            roll_window = st.slider("滾動視窗大小（交易日）", 30, 120, 60, step=10)
            roll_lag = st.slider("固定落後期數", 1, 5, 1)

            if len(aligned) < roll_window + 10:
                st.warning("資料不足以執行滾動分析，請縮短視窗或延長資料期間。")
            else:
                with st.spinner("計算滾動格蘭傑因果..."):
                    roll_s2r = rolling_granger(aligned["sentiment"], aligned["returns"],
                                                window=roll_window, lag=roll_lag)
                    roll_r2s = rolling_granger(aligned["returns"], aligned["sentiment"],
                                                window=roll_window, lag=roll_lag)

                fig_roll = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                          vertical_spacing=0.06,
                                          subplot_titles=["收盤價", "情緒→報酬 P 值", "報酬→情緒 P 值"],
                                          row_heights=[0.35, 0.325, 0.325])
                fig_roll.add_trace(go.Scatter(x=df.index, y=df["close"], name="收盤價",
                                               line=dict(color="#42a5f5")), row=1, col=1)
                # P-value traces
                for roll_df, color, name, row in [
                    (roll_s2r, "#26a69a", "情緒→報酬", 2),
                    (roll_r2s, "#ffa726", "報酬→情緒", 3),
                ]:
                    fig_roll.add_trace(go.Scatter(
                        x=roll_df.index, y=roll_df["p_value"],
                        name=name, line=dict(color=color, width=1.5),
                    ), row=row, col=1)
                    # Shade significant regions
                    sig_mask = roll_df["significant"].fillna(False)
                    if sig_mask.any():
                        fig_roll.add_trace(go.Scatter(
                            x=roll_df.index, y=np.where(sig_mask, roll_df["p_value"], np.nan),
                            fill="tozeroy", fillcolor=f"{color}33",
                            line=dict(color=color, width=0), showlegend=False,
                        ), row=row, col=1)
                    fig_roll.add_hline(y=0.05, line_dash="dash", line_color="#ef5350", row=row, col=1)

                fig_roll.update_layout(
                    height=580, template="plotly_dark",
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                )
                st.plotly_chart(fig_roll, use_container_width=True)
                st.caption("綠色填滿區域 = P < 0.05（格蘭傑因果顯著區間）")

        # ── Sub-tab 4: Predictive Score ─────────────────────────────────────
        with subtab4:
            st.markdown("### 🎯 情緒預測力評分")
            st.markdown("衡量情緒指標在不同領先期下對股價報酬方向的**實際預測能力**。")

            opt_lead = granger_result.get("lead_lag", {}).get("optimal_lead") or 1
            eval_lead = st.slider("評估領先期 k", 1, max_granger_lag, opt_lead)

            with st.spinner("計算預測力指標..."):
                scores = [
                    sentiment_predictive_score(aligned["sentiment"], aligned["returns"], lead_k=k)
                    for k in range(1, max_granger_lag + 1)
                ]
            scores_df = pd.DataFrame([s for s in scores if "error" not in s])

            if not scores_df.empty:
                c1, c2, c3 = st.columns(3)
                sel = scores_df[scores_df["lead_k"] == eval_lead].iloc[0]
                c1.metric("方向準確率", f"{sel['direction_accuracy']:.1%}",
                           delta=f"{sel['direction_accuracy']-0.5:+.1%} vs 隨機")
                c2.metric("Spearman IC", f"{sel['spearman_ic']:.4f}",
                           delta="顯著" if sel["ic_p_value"] < 0.05 else "不顯著")
                c3.metric("資訊比率 (IR)", f"{sel['information_ratio']:.3f}")

                st.markdown("---")
                ca, cb = st.columns(2)
                with ca:
                    fig_acc = px.line(scores_df, x="lead_k", y="direction_accuracy",
                                       title="方向準確率 vs 領先期數",
                                       template="plotly_dark",
                                       labels={"lead_k": "領先期數 k", "direction_accuracy": "方向準確率"},
                                       color_discrete_sequence=["#42a5f5"])
                    fig_acc.add_hline(y=0.5, line_dash="dash", line_color="#78909c", annotation_text="隨機基準")
                    fig_acc.update_layout(height=300, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_acc, use_container_width=True)
                with cb:
                    fig_ic = px.bar(scores_df, x="lead_k", y="spearman_ic",
                                     title="Spearman IC vs 領先期數",
                                     template="plotly_dark",
                                     color="is_informative",
                                     color_discrete_map={True: "#26a69a", False: "#546e7a"},
                                     labels={"lead_k": "領先期數 k", "spearman_ic": "Spearman IC"})
                    fig_ic.add_hline(y=0, line_color="#ffffff")
                    fig_ic.update_layout(height=300, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_ic, use_container_width=True)

                # Quintile return chart
                q_returns = sel.get("quintile_returns", {})
                if q_returns:
                    q_df = pd.DataFrame(list(q_returns.items()), columns=["分位數", "平均報酬"])
                    q_df["分位數"] = q_df["分位數"].map(
                        {0: "Q1最悲觀", 1: "Q2", 2: "Q3", 3: "Q4", 4: "Q5最樂觀"}
                    )
                    fig_q = px.bar(q_df, x="分位數", y="平均報酬",
                                    title=f"情緒分位數 vs 次 {eval_lead} 日平均報酬率",
                                    template="plotly_dark",
                                    color="平均報酬",
                                    color_continuous_scale=["#ef5350", "#78909c", "#26a69a"])
                    fig_q.add_hline(y=0, line_color="#ffffff")
                    fig_q.update_layout(height=300, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
                    st.plotly_chart(fig_q, use_container_width=True)

# ── Tab 4: Signal Summary ─────────────────────────────────────────────────────
with tab4:
    st.markdown("## 📋 技術指標訊號摘要")
    signals = get_signal_summary(df)
    signal_map = {
        "bullish": ("🟢", "看多", "signal-bull"),
        "bearish": ("🔴", "看空", "signal-bear"),
        "overbought": ("🟡", "超買", "signal-neutral"),
        "oversold": ("🟣", "超賣", "signal-neutral"),
        "neutral": ("⚪", "中性", "signal-neutral"),
    }
    cols = st.columns(2)
    for i, (indicator, (status, description)) in enumerate(signals.items()):
        icon, label, css = signal_map.get(status, ("⚪", status, "signal-neutral"))
        with cols[i % 2]:
            st.markdown(f"""
<div class="metric-card">
    <b>{indicator.upper()}</b><br>
    {icon} <span class="{css}">{label}</span><br>
    <small>{description}</small>
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 近期技術數據")
    display_cols = ["close", "ma5", "ma20", "ma60", "rsi", "macd", "macd_signal", "bb_upper", "bb_lower", "atr"]
    display_df = df[display_cols].tail(20).round(3)
    display_df.columns = ["收盤", "MA5", "MA20", "MA60", "RSI", "MACD", "Signal", "BB上", "BB下", "ATR"]
    st.dataframe(display_df.style.background_gradient(subset=["RSI"], cmap="RdYlGn"), use_container_width=True)

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#546e7a; font-size:12px;'>"
    "台股情緒分析系統 | 資料來源：Yahoo Finance | 情緒分析：模擬資料（示範用途）"
    "</div>",
    unsafe_allow_html=True,
)
