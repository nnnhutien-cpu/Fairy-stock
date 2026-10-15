# ==================================================================================
# TAB KHUYẾN NGHỊ ICHIMOKU — Cô Tiên Stock
#
# Dùng ĐÚNG bộ quy tắc Ichimoku đã có trong repo, không tạo hệ mới:
#   • Vào/thoát trend: market_trend_signal.get_trend_signal (giống backtester.py)
#       VÀO  : giá > đỉnh mây + Vol >= 1.2x MA20 + Tenkan > Kijun
#       THOÁT: đóng cửa < Kijun HOẶC < đáy mây
#   • Kết thúc trend sớm: Chikou chui vào mây (knowledge_tab.py, mục II)
#   • Vùng đỉnh: giá cách đường 129 nến > 30% (knowledge_tab.py, mục II)
# Thêm 5 điều kiện Ichimoku cổ điển để chấm điểm -5..+5 (độ đồng thuận).
# ==================================================================================

import concurrent.futures

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import ui_kit
from market_trend_signal import get_trend_signal

VOL_OK = 1.2          # Vol / MA20 tối thiểu để xác nhận (giống backtester)
PULLBACK_MAX = 3.0    # % trên Kijun được coi là "pullback về Kijun"
OVEREXT_KIJUN = 10.0  # % trên Kijun -> không mua đuổi
OVEREXT_129 = 30.0    # % trên đường 129 nến -> vùng đỉnh

# Thứ tự ưu tiên khi sắp xếp bảng quét
RANK = ["MUA MẠNH", "MUA GIA TĂNG", "MUA", "CHỜ VOL", "THEO DÕI", "GIỮ", "GIẢM TỶ TRỌNG",
        "ĐỨNG NGOÀI", "BÁN", "TRÁNH"]


def _label_rank(label: str) -> int:
    up = label.upper()
    return next((i for i, k in enumerate(RANK) if k in up), len(RANK))


def compute_ichimoku_reco(df, ticker, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """Trả về dict khuyến nghị Ichimoku cho phiên mới nhất, hoặc None nếu thiếu dữ liệu."""
    if df is None or len(df) < p_senkou_b + p_shift + 5:
        return None

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if 'time' not in df.columns and 'date' in df.columns:
        df['time'] = df['date']
    df = df.reset_index(drop=True)

    hh = lambda n: df['high'].rolling(n).max()
    ll = lambda n: df['low'].rolling(n).min()
    df['tenkan'] = (hh(p_tenkan) + ll(p_tenkan)) / 2
    df['kijun'] = (hh(p_kijun) + ll(p_kijun)) / 2
    df['span_a_raw'] = (df['tenkan'] + df['kijun']) / 2          # mây tương lai (chưa dời)
    df['span_b_raw'] = (hh(p_senkou_b) + ll(p_senkou_b)) / 2
    df['senkou_a'] = df['span_a_raw'].shift(p_shift)              # mây hiện tại
    df['senkou_b'] = df['span_b_raw'].shift(p_shift)
    df['cloud_top'] = df[['senkou_a', 'senkou_b']].max(axis=1)
    df['cloud_bot'] = df[['senkou_a', 'senkou_b']].min(axis=1)
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['line129'] = (hh(129) + ll(129)) / 2 if len(df) >= 129 else np.nan

    last = df.iloc[-1]
    close = float(last['close'])
    tenkan, kijun = float(last['tenkan']), float(last['kijun'])
    c_top, c_bot = float(last['cloud_top']), float(last['cloud_bot'])
    if any(np.isnan(x) for x in (tenkan, kijun, c_top, c_bot)):
        return None

    v_ratio = float(last['volume'] / last['vol_ma20']) if last['vol_ma20'] > 0 else 0.0
    pct_kijun = (close - kijun) / kijun * 100
    pct_129 = (close - last['line129']) / last['line129'] * 100 if pd.notna(last['line129']) else np.nan

    # ── 5 điều kiện Ichimoku: +1 tăng / 0 trung tính / -1 giảm ───────────────
    checks = []
    if close > c_top:
        checks.append(("Giá so với mây", 1, f"Trên mây (đỉnh mây {c_top:,.2f})"))
    elif close < c_bot:
        checks.append(("Giá so với mây", -1, f"Dưới mây (đáy mây {c_bot:,.2f})"))
    else:
        checks.append(("Giá so với mây", 0, f"Trong mây ({c_bot:,.2f} – {c_top:,.2f})"))

    checks.append(("Tenkan / Kijun", 1 if tenkan > kijun else (-1 if tenkan < kijun else 0),
                   f"Tenkan {tenkan:,.2f} {'>' if tenkan > kijun else '<' if tenkan < kijun else '='} Kijun {kijun:,.2f}"))

    # Chikou = giá hôm nay đặt lùi 26 phiên -> so với giá & mây tại phiên t-26
    past = df.iloc[-1 - p_shift]
    chikou_in_cloud = False
    if close > past['close'] and close > past['cloud_top']:
        checks.append(("Chikou", 1, "Trên giá và trên mây 26 phiên trước"))
    elif close < past['close'] and close < past['cloud_bot']:
        checks.append(("Chikou", -1, "Dưới giá và dưới mây 26 phiên trước"))
    else:
        chikou_in_cloud = past['cloud_bot'] <= close <= past['cloud_top']
        checks.append(("Chikou", 0, "Đang trong mây quá khứ" if chikou_in_cloud else "Vướng giá quá khứ"))

    fa, fb = float(last['span_a_raw']), float(last['span_b_raw'])
    checks.append(("Mây tương lai", 1 if fa > fb else -1,
                   "Mây xanh (Span A > Span B)" if fa > fb else "Mây đỏ (Span A < Span B)"))

    k_prev = df['kijun'].iloc[-6]
    checks.append(("Hướng Kijun", 1 if kijun > k_prev else (-1 if kijun < k_prev else 0),
                   "Đi lên (5 phiên)" if kijun > k_prev else ("Đi xuống (5 phiên)" if kijun < k_prev else "Đi ngang")))

    score = sum(c[1] for c in checks)

    # ── Trạng thái trend theo đúng quy tắc backtester ────────────────────────
    sig = get_trend_signal(df[['time', 'open', 'high', 'low', 'close', 'volume']],
                           p_tenkan, p_kijun, p_senkou_b, p_shift)
    in_trend = bool(sig and sig.in_trend)
    today = sig.current_date if sig else ""
    new_entry = in_trend and sig.entry_date == today
    new_exit = (not in_trend) and sig is not None and sig.exit_date == today

    above, inside = close > c_top, c_bot <= close <= c_top
    tk_up = tenkan > kijun
    stop = max(kijun, c_bot)                     # mức thoát gần nhất theo quy tắc
    stop_pct = (stop - close) / close * 100
    notes = []

    # ── Ra khuyến nghị ────────────────────────────────────────────────────────
    if new_exit:
        label, desc = "🔴 BÁN", f"Tín hiệu thoát trend hôm nay: {sig.exit_reason}."
    elif new_entry:
        if score == 5 and pct_kijun <= OVEREXT_KIJUN / 2:
            label, desc = "🟢 MUA MẠNH (30%)", "Phá mây + vol xác nhận, đủ 5/5 điều kiện Ichimoku, giá còn gần Kijun."
        else:
            label, desc = "🟢 MUA (20%)", "Tín hiệu vào trend mới: phá mây + Vol ≥ 1.2x MA20 + Tenkan > Kijun."
    elif in_trend:
        if chikou_in_cloud:
            label, desc = "🟠 GIẢM TỶ TRỌNG", "Đang trong trend nhưng Chikou chui vào mây — dấu hiệu kết thúc trend sớm."
        elif pct_kijun > OVEREXT_KIJUN:
            label, desc = "⏸️ GIỮ", f"Trong trend, giá cách Kijun {pct_kijun:.1f}% — không mua đuổi, chờ pullback."
        elif 0 <= pct_kijun <= PULLBACK_MAX and tk_up and score >= 3:
            label, desc = "🟢 MUA GIA TĂNG (10%)", "Trong trend, giá pullback về sát Kijun mà cấu trúc vẫn tăng."
        else:
            label, desc = "⏸️ GIỮ", "Đang trong trend tăng, giữ đến khi gãy Kijun hoặc đáy mây."
    else:
        if above and tk_up:
            label, desc = "👀 CHỜ VOL", f"Giá trên mây, Tenkan > Kijun nhưng Vol mới {v_ratio:.2f}x MA20 — chờ phiên ≥ {VOL_OK}x."
        elif inside and tk_up and fa > fb:
            label, desc = "👀 THEO DÕI", "Giá trong mây, Tenkan > Kijun, mây tương lai xanh — có thể sắp phá mây."
        elif close < c_bot and score <= -3:
            label, desc = "🔴 TRÁNH", "Dưới mây, đa số điều kiện Ichimoku đang giảm."
        else:
            label, desc = "⏸️ ĐỨNG NGOÀI", "Chưa có điều kiện vào trend theo Ichimoku."

    if pd.notna(pct_129) and pct_129 > OVEREXT_129:
        notes.append(f"⚠️ Giá cách đường 129 nến {pct_129:.1f}% (> {OVEREXT_129:.0f}%) → vùng đỉnh, ưu tiên chốt lời")
        if "MUA" in label:
            label, desc = "⏸️ GIỮ", desc + " Tuy nhiên giá đã ở vùng đỉnh so với đường 129 nến — không mua mới."
    if in_trend or "MUA" in label:
        notes.append(f"🛑 Mức thoát: {stop:,.2f} ({stop_pct:+.1f}%) — đóng cửa dưới Kijun hoặc đáy mây")

    return {
        "ticker": ticker, "df": df, "close": close, "date": today,
        "label": label, "desc": desc, "notes": notes, "checks": checks, "score": score,
        "tenkan": tenkan, "kijun": kijun, "cloud_top": c_top, "cloud_bot": c_bot,
        "v_ratio": v_ratio, "pct_kijun": pct_kijun, "pct_129": pct_129,
        "stop": stop, "stop_pct": stop_pct, "in_trend": in_trend, "signal": sig,
    }


# ==================================================================================
# GIAO DIỆN
# ==================================================================================

def _color(label):
    up = label.upper()
    if "MUA" in up:
        return ui_kit.UP
    if "BÁN" in up or "TRÁNH" in up:
        return ui_kit.DOWN
    if "GIẢM TỶ TRỌNG" in up:
        return "#ea580c"
    if "CHỜ VOL" in up or "THEO DÕI" in up:
        return ui_kit.WARN
    return ui_kit.MUTED


def _render_chart(r, p_shift=26, bars=120):
    df = r["df"]
    hist = df.tail(bars).copy()
    x = pd.to_datetime(hist['time']).dt.strftime('%Y-%m-%d').tolist()
    n = len(hist)

    # Mây tương lai: p_shift phiên tiếp theo (trục category -> nhãn T+1..T+26)
    fut_a = df['span_a_raw'].tail(p_shift).tolist()
    fut_b = df['span_b_raw'].tail(p_shift).tolist()
    x_all = x + [f"T+{i}" for i in range(1, p_shift + 1)]
    span_a = hist['senkou_a'].tolist() + fut_a
    span_b = hist['senkou_b'].tolist() + fut_b
    chikou = hist['close'].shift(-p_shift).tolist()   # giá đặt lùi 26 phiên

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.78, 0.22], subplot_titles=["Ichimoku", "Volume vs MA20"])

    fig.add_trace(go.Scatter(x=x_all, y=span_a, line=dict(color='rgba(22,163,74,.6)', width=1),
                             name='Senkou A'), row=1, col=1)
    fig.add_trace(go.Scatter(x=x_all, y=span_b, line=dict(color='rgba(220,38,38,.6)', width=1),
                             fill='tonexty', fillcolor='rgba(124,58,237,.07)', name='Senkou B'), row=1, col=1)
    fig.add_trace(go.Candlestick(
        x=x, open=hist['open'], high=hist['high'], low=hist['low'], close=hist['close'],
        increasing_line_color=ui_kit.UP, increasing_fillcolor=ui_kit.UP,
        decreasing_line_color=ui_kit.DOWN, decreasing_fillcolor=ui_kit.DOWN,
        name='Giá', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['tenkan'], line=dict(color=ui_kit.SERIES[0], width=1.5),
                             name='Tenkan'), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['kijun'], line=dict(color=ui_kit.SERIES[1], width=2.2),
                             name='Kijun'), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=chikou, line=dict(color=ui_kit.SERIES[5], width=1.2, dash='dot'),
                             name='Chikou'), row=1, col=1)

    sig = r["signal"]
    if r["in_trend"] and sig and sig.entry_price:
        fig.add_hline(y=sig.entry_price, line_dash="dash", line_color=ui_kit.UP, row=1, col=1,
                      annotation_text=f"Vào {sig.entry_date}", annotation_font_color=ui_kit.UP)
    if r["in_trend"] or "MUA" in r["label"]:
        fig.add_hline(y=r["stop"], line_dash="dot", line_color=ui_kit.DOWN, row=1, col=1,
                      annotation_text="Mức thoát", annotation_font_color=ui_kit.DOWN)

    vol_colors = [ui_kit.UP if c >= o else ui_kit.DOWN for c, o in zip(hist['close'], hist['open'])]
    fig.add_trace(go.Bar(x=x, y=hist['volume'], marker_color=vol_colors, opacity=.6,
                         name='Volume', showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=hist['vol_ma20'] * VOL_OK, line=dict(color=ui_kit.WARN, width=1.5, dash='dot'),
                             name=f'{VOL_OK}x MA20'), row=2, col=1)

    ui_kit.style_fig(fig, 640, dates=False)
    fig.update_xaxes(type="category", nticks=8)
    ui_kit.plot(fig)


def _render_single(r):
    color = _color(r["label"])
    st.markdown(f"""
    <div class="lk-card" style="border-left:4px solid {color};">
        <div class="lk-label">Ichimoku · {r['ticker']} · giá {r['close']:,.2f} · {r['date']}</div>
        <div style="font-size:1.6rem;font-weight:800;color:{color};margin-top:4px;">{r['label']}</div>
        <div style="font-size:0.92rem;color:var(--text);margin-top:6px;">{r['desc']}</div>
    </div>
    """, unsafe_allow_html=True)

    sig = r["signal"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("☁️ Điểm Ichimoku", f"{r['score']:+d} / 5")
    if r["in_trend"] and sig and sig.entry_price:
        c2.metric("📈 Trạng thái", "Trong trend",
                  f"{(r['close'] - sig.entry_price) / sig.entry_price * 100:+.1f}% từ {sig.entry_date}")
    else:
        c2.metric("📈 Trạng thái", "Đứng ngoài",
                  f"Thoát {sig.exit_date} ({sig.exit_change_pct:+.1f}%)" if sig and sig.exit_date else None,
                  delta_color="off")
    c3.metric("📏 Cách Kijun", f"{r['pct_kijun']:+.2f}%")
    c4.metric("📦 Vol / MA20", f"{r['v_ratio']:.2f}x", "Đạt" if r['v_ratio'] >= VOL_OK else "Chưa đạt",
              delta_color="normal" if r['v_ratio'] >= VOL_OK else "off")

    for n in r["notes"]:
        st.markdown(f"- {n}")

    ui_kit.section("✅ 5 điều kiện Ichimoku")
    icon = {1: "🟢", 0: "⚪", -1: "🔴"}
    st.dataframe(pd.DataFrame([{"": icon[v], "Điều kiện": k, "Chi tiết": d} for k, v, d in r["checks"]]),
                 hide_index=True, width="stretch")

    ui_kit.section(f"📊 Biểu đồ Ichimoku {r['ticker']} (120 phiên + mây 26 phiên tới)")
    _render_chart(r)


def _scan(tickers, get_stock_data_fn, params):
    def one(t):
        try:
            r = compute_ichimoku_reco(get_stock_data_fn(t, days_back=500), t, *params)
        except Exception:
            return None
        if r is None:
            return None
        sig = r["signal"]
        return {
            "Mã CP": t,
            "Giá": round(r["close"], 2),
            "Khuyến nghị": r["label"],
            "Điểm": r["score"],
            "Ngày vào trend": sig.entry_date if r["in_trend"] and sig else "",
            "% từ điểm vào": round((r["close"] - sig.entry_price) / sig.entry_price * 100, 1)
            if r["in_trend"] and sig and sig.entry_price else None,
            "Cách Kijun %": round(r["pct_kijun"], 1),
            "Vol x MA20": round(r["v_ratio"], 2),
            "Mức thoát": round(r["stop"], 2),
        }

    rows = []
    prog = st.progress(0.0, text="Đang quét Ichimoku...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futures = [ex.submit(one, t) for t in tickers]
        for i, f in enumerate(concurrent.futures.as_completed(futures), 1):
            row = f.result()
            if row:
                rows.append(row)
            prog.progress(i / len(futures), text=f"Đang quét Ichimoku... {i}/{len(futures)}")
    prog.empty()
    out = pd.DataFrame(rows)
    if not out.empty:
        out["_r"] = out["Khuyến nghị"].map(_label_rank)
        out = out.sort_values(["_r", "Điểm"], ascending=[True, False]).drop(columns="_r")
    return out


def render_ichimoku_tab(get_stock_data_fn, watchlist, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    ui_kit.page_header("☁️ Khuyến Nghị Ichimoku",
                       f"Vào: phá mây + Vol ≥ {VOL_OK}x MA20 + Tenkan>Kijun · Thoát: gãy Kijun / đáy mây "
                       f"· Tham số {p_tenkan}-{p_kijun}-{p_senkou_b}-{p_shift}")
    params = (p_tenkan, p_kijun, p_senkou_b, p_shift)

    mode = st.segmented_control("Chế độ", ["🔎 Một mã", "📋 Quét danh sách"], default="🔎 Một mã",
                                key="ichi_mode", label_visibility="collapsed")

    if mode == "📋 Quét danh sách":
        st.caption(f"Quét {len(watchlist)} mã thanh khoản cao (danh sách ưu tiên).")
        if st.button("⚡ QUÉT ICHIMOKU", type="primary", width="stretch"):
            st.session_state["ichi_scan"] = _scan(watchlist, get_stock_data_fn, params)
        res = st.session_state.get("ichi_scan")
        if res is not None:
            if res.empty:
                st.warning("Không lấy được dữ liệu mã nào.")
            else:
                only_buy = st.toggle("Chỉ hiện mã có tín hiệu MUA / CHỜ VOL / THEO DÕI", value=False)
                show = res[res["Khuyến nghị"].str.contains("MUA|CHỜ VOL|THEO DÕI")] if only_buy else res
                st.dataframe(show, hide_index=True, width="stretch", height=min(38 * (len(show) + 1), 720))
        else:
            ui_kit.note("Bấm <b>⚡ QUÉT ICHIMOKU</b> để chấm khuyến nghị cho cả danh sách.")
    else:
        try:
            from data_loader import get_all_tickers
            codes = sorted(set(get_all_tickers("all")))
        except Exception:
            codes = []
        default = st.session_state.get("ichi_last_ticker", "HPG")
        ticker = st.selectbox("Mã cổ phiếu", options=codes or [default],
                              index=codes.index(default) if default in codes else 0,
                              accept_new_options=True, key="ichi_ticker",
                              placeholder="Gõ mã, ví dụ HPG, FPT…")
        ticker = str(ticker or "").upper().strip()
        if not ticker:
            return
        st.session_state["ichi_last_ticker"] = ticker

        with st.spinner(f"Đang tính Ichimoku cho {ticker}..."):
            df = get_stock_data_fn(ticker, days_back=500)
            r = compute_ichimoku_reco(df, ticker, *params)
        if r is None:
            st.error(f"⚠️ Không đủ dữ liệu cho **{ticker}** (cần ≥ {p_senkou_b + p_shift + 5} phiên).")
            return
        _render_single(r)

    with st.expander("📖 Bảng quy tắc khuyến nghị Ichimoku"):
        st.markdown(f"""
| Khuyến nghị | Điều kiện | Tỷ trọng |
|---|---|---|
| 🟢 **MUA MẠNH** | Tín hiệu vào trend HÔM NAY + đủ 5/5 điều kiện + giá cách Kijun ≤ {OVEREXT_KIJUN/2:.0f}% | 30% |
| 🟢 **MUA** | Tín hiệu vào trend HÔM NAY: giá > đỉnh mây + Vol ≥ {VOL_OK}x MA20 + Tenkan > Kijun | 20% |
| 🟢 **MUA GIA TĂNG** | Đang trong trend, giá pullback về 0–{PULLBACK_MAX:.0f}% trên Kijun, Tenkan > Kijun, điểm ≥ +3 | 10% |
| ⏸️ **GIỮ** | Đang trong trend; hoặc giá cách Kijun > {OVEREXT_KIJUN:.0f}% (không mua đuổi) | — |
| 🟠 **GIẢM TỶ TRỌNG** | Đang trong trend nhưng Chikou chui vào mây (kết thúc trend sớm) | — |
| 👀 **CHỜ VOL** | Giá trên mây, Tenkan > Kijun, nhưng Vol chưa đạt {VOL_OK}x MA20 | — |
| 👀 **THEO DÕI** | Giá trong mây, Tenkan > Kijun, mây tương lai xanh | — |
| ⏸️ **ĐỨNG NGOÀI** | Chưa đủ điều kiện | — |
| 🔴 **BÁN** | HÔM NAY đóng cửa dưới Kijun hoặc dưới đáy mây (khi đang trong trend) | — |
| 🔴 **TRÁNH** | Dưới mây và điểm ≤ −3 | — |

**Điểm Ichimoku (−5…+5)**: giá vs mây · Tenkan vs Kijun · Chikou vs giá/mây 26 phiên trước · màu mây tương lai · hướng Kijun.
**Vùng đỉnh**: giá cách đường 129 nến > {OVEREXT_129:.0f}% → mọi tín hiệu MUA hạ xuống GIỮ.
Tín hiệu mang tính THAM KHẢO kỹ thuật, không phải khuyến nghị đầu tư.
        """)
