"""
tab_tin_hieu_ngay.py
====================================================================
TÍN HIỆU KHUYẾN NGHỊ KHUNG NGÀY: ĐIỂM VÀO / ĐIỂM RA (mô phỏng thẻ tham khảo)

Dùng dữ liệu ngày từ data_loader.get_stock_data (cache Supabase -> TCBS/DNSE),
KHÔNG cần dữ liệu intraday nên ổn định hơn tab 5 phút.

LUẬT (suy ra từ ảnh tham khảo + luật backtest Ichimoku/Volume của bạn):
  Đường dài  : "đường 129" = (đỉnh cao nhất + đáy thấp nhất) / 2 của 129 phiên
               (kiểu Kijun 129) - đường đỏ dạng bậc thang trong ảnh.  [GIẢ ĐỊNH]
  MUA (vào)  : nến tăng + đóng cửa > đường 129 + Volume >= 1.2 x MA20
               + đóng cửa vượt đỉnh đóng cửa 20 phiên trước.          [TỰ ĐẶT]
  Giá vào    : chân nến tín hiệu (giá mở cửa của nến tăng).
  THOÁT 3 TẦNG (xét theo GIÁ ĐÓNG CỬA nến ngày):
     Tầng 1 (30%): đóng cửa < đáy ngắn hạn (đáy thấp nhất 5 phiên gần nhất kể từ lúc vào)
     Tầng 2 (30%): đóng cửa < chân nến vào lệnh
     Tầng 3 (40% còn lại): đóng cửa < đường 129
Tín hiệu chỉ mang tính THAM KHẢO, không phải tư vấn đầu tư.
====================================================================
"""
import concurrent.futures

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data_loader import get_stock_data, get_data_freshness

W_T1, W_T2 = 0.30, 0.30          # tỷ trọng bán tầng 1, tầng 2 (tầng 3 = phần còn lại 40%)


# ==========================================================
# 1. ĐỘNG CƠ TÍN HIỆU (thuần pandas/numpy, không phụ thuộc Streamlit)
# ==========================================================
def analyze_signal(df, p_line=129, p_vol=20, vol_mult=1.2, p_break=20, p_swing=5):
    if df is None or len(df) == 0:
        return None
    d = df.copy()
    d = d.sort_values("time").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    d["volume"] = d["volume"].fillna(0)
    n = len(d)
    if n < p_line + 5:
        return None

    d["line"] = (d["high"].rolling(p_line).max() + d["low"].rolling(p_line).min()) / 2
    d["vol_ma"] = d["volume"].rolling(p_vol).mean()
    d["prior_high"] = d["close"].shift(1).rolling(p_break).max()
    trig = (
        (d["close"] > d["open"])
        & (d["close"] > d["line"])
        & (d["volume"] >= vol_mult * d["vol_ma"])
        & (d["close"] > d["prior_high"])
    ).fillna(False).to_numpy()

    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    line = d["line"].to_numpy(float)

    trades, pos = [], None
    for i in range(p_line, n):
        if pos is None:
            if trig[i]:
                pos = {"entry_i": i, "entry": o[i], "w": 1.0, "t1": False, "t2": False, "exits": []}
            continue

        e = pos["entry_i"]
        lvl1 = l[max(e, i - p_swing):i].min()      # đáy ngắn hạn tính tới hôm qua
        base = pos["entry"]
        ln = line[i - 1]
        px = c[i]

        if not pos["t1"] and px < lvl1:
            pos["t1"] = True
            pos["exits"].append((i, px, W_T1, "Tầng 1"))
            pos["w"] -= W_T1
        if not pos["t2"] and px < base:
            pos["t2"] = True
            pos["exits"].append((i, px, W_T2, "Tầng 2"))
            pos["w"] -= W_T2
        if px < ln:
            pos["exits"].append((i, px, pos["w"], "Tầng 3 (thủng đường 129)"))
            pos["w"] = 0.0
            trades.append(pos)
            pos = None

    last_close = float(c[-1])
    res = {
        "df": d, "n": n, "last_close": last_close,
        "last_date": d["time"].iloc[-1], "params": dict(p_line=p_line, p_swing=p_swing),
    }

    if pos is not None:
        e = pos["entry_i"]
        res.update(
            status="BUY",
            entry_i=e,
            entry_date=d["time"].iloc[e],
            entry_price=float(pos["entry"]),
            pnl_pct=(last_close / pos["entry"] - 1) * 100,
            sessions=n - e,
            lvl1=float(l[max(e, n - p_swing):n].min()),
            lvl1_date=d["time"].iloc[max(e, n - p_swing) + int(np.argmin(l[max(e, n - p_swing):n]))],
            lvl2=float(pos["entry"]),
            lvl3=float(line[-1]),
            t1_done=pos["t1"], t2_done=pos["t2"],
            remaining=pos["w"],
        )
    else:
        res.update(status="WAIT", entry_i=None, lvl3=float(line[-1]))
        if trades:
            t = trades[-1]
            realized = sum(w * (px / t["entry"] - 1) for _, px, w, _ in t["exits"]) * 100
            res["last_trade"] = {
                "entry_date": d["time"].iloc[t["entry_i"]],
                "entry_price": float(t["entry"]),
                "exit_date": d["time"].iloc[t["exits"][-1][0]],
                "pnl_pct": realized,
            }
    return res


# ==========================================================
# 2. QUÉT NHIỀU MÃ
# ==========================================================
def _summarize(ticker, res):
    if res is None:
        return {"Mã": ticker, "Trạng thái": "Thiếu dữ liệu"}
    row = {"Mã": ticker, "Giá": round(res["last_close"], 2)}
    if res["status"] == "BUY":
        row.update({
            "Trạng thái": "ĐANG BUY",
            "Ngày vào": res["entry_date"].strftime("%d/%m/%Y"),
            "Giá vào": round(res["entry_price"], 2),
            "Lãi/lỗ %": round(res["pnl_pct"], 2),
            "Số phiên": res["sessions"],
            "SL sớm (30%)": round(res["lvl1"], 2),
            "SL tiếp (30%)": round(res["lvl2"], 2),
            "Thoát hết (40%)": round(res["lvl3"], 2),
        })
    else:
        row.update({"Trạng thái": "Chờ tín hiệu", "Thoát hết (40%)": round(res["lvl3"], 2)})
    return row


@st.cache_data(ttl=600, show_spinner=False)
def scan_signals(tickers: tuple, p_line, vol_mult, p_break, p_swing):
    def work(t):
        try:
            df = get_stock_data(t, days_back=400)
            return _summarize(t, analyze_signal(df, p_line=p_line, vol_mult=vol_mult,
                                                p_break=p_break, p_swing=p_swing))
        except Exception:
            return {"Mã": t, "Trạng thái": "Lỗi dữ liệu"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(work, tickers))


# ==========================================================
# 3. BIỂU ĐỒ + THẺ
# ==========================================================
def build_chart(res, n_bars=110):
    d = res["df"].tail(n_bars).reset_index(drop=True)
    off = res["n"] - len(d)
    x = d["time"].dt.strftime("%d/%m/%y")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
                        vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=x, open=d["open"], high=d["high"], low=d["low"], close=d["close"],
        increasing_line_color="#22c55e", increasing_fillcolor="#22c55e",
        decreasing_line_color="#ef4444", decreasing_fillcolor="#ef4444",
        name="Giá", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=d["line"], mode="lines", line=dict(color="#ef4444", width=2, shape="hv"),
        name="Đường 129"), row=1, col=1)

    vcol = np.where(d["close"] >= d["open"], "rgba(34,197,94,.65)", "rgba(239,68,68,.65)")
    fig.add_trace(go.Bar(x=x, y=d["volume"], marker_color=vcol, name="Volume",
                         showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=d["vol_ma"], mode="lines",
                             line=dict(color="#a78bfa", width=1.5), name="MA20 Vol",
                             showlegend=False), row=2, col=1)

    if res["status"] == "BUY":
        k = res["entry_i"] - off
        k0 = max(k, 0)
        fig.add_vrect(x0=x.iloc[k0], x1=x.iloc[-1], fillcolor="rgba(34,197,94,.10)",
                      line_width=0, row=1, col=1)
        if k >= 0:
            fig.add_annotation(
                x=x.iloc[k], y=float(d["low"].iloc[k]), ax=0, ay=45,
                text=f"Điểm vào<br>{res['entry_date']:%d/%m/%y} {res['entry_price']:.2f}",
                showarrow=True, arrowhead=2, arrowwidth=2, arrowcolor="#22c55e",
                font=dict(color="#22c55e", size=11), row=1, col=1)
        for lvl, dash, col in ((res["lvl1"], "dash", "#f59e0b"),
                               (res["lvl2"], "dot", "#fbbf24")):
            fig.add_shape(type="line", x0=x.iloc[k0], x1=x.iloc[-1], y0=lvl, y1=lvl,
                          line=dict(color=col, width=1.4, dash=dash), row=1, col=1)

    fig.update_layout(
        template="plotly_dark", height=520, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02),
        font=dict(family="Sora, sans-serif", size=11),
    )
    fig.update_xaxes(type="category", nticks=8, showgrid=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.06)")
    return fig


def _fmt(x):
    return f"{x:,.2f}"


def render_card(ticker, res):
    fresh = get_data_freshness(res["df"])
    if res["status"] == "BUY":
        pnl_cls = "val-up" if res["pnl_pct"] >= 0 else "val-down"
        t1 = " <i>(đã kích hoạt)</i>" if res["t1_done"] else ""
        t2 = " <i>(đã kích hoạt)</i>" if res["t2_done"] else ""
        left = int(round(res["remaining"] * 100))
        st.markdown(f"""
<div class="lk-card">
  <div><span class="badge-fib">KHUNG NGÀY</span>
       &nbsp;<span class="lk-ticker" style="font-size:22px">{ticker}</span>
       &nbsp;<span class="val-up" style="font-size:20px;font-weight:800">🟢 ĐANG BUY</span>
       <span style="color:#aaa"> @ {_fmt(res['last_close'])}</span></div>
  <div class="lk-company">Vào từ {res['entry_date']:%d/%m/%Y} @ {_fmt(res['entry_price'])}
       · lãi mở <b class="{pnl_cls}">{res['pnl_pct']:+.2f}%</b> · giữ {res['sessions']} phiên
       · còn giữ {left}% vị thế</div>
  <div class="formula-note" style="margin-top:6px">
    🟠 <b>Stop Loss sớm 30%</b> nếu nến ngày đóng cửa dưới <b>{_fmt(res['lvl1'])}</b>
       (đáy ngắn hạn {res['lvl1_date']:%d/%m/%y}){t1}<br>
    🟡 <b>Stop Loss 30% tiếp theo</b> nếu nến ngày đóng cửa dưới <b>{_fmt(res['lvl2'])}</b>
       (chân nến vào {res['entry_date']:%d/%m/%y}){t2}<br>
    🔴 <b>Thoát HẾT (40% còn lại)</b> nếu nến ngày đóng cửa dưới đường 129
       (<b>{_fmt(res['lvl3'])}</b>)
  </div>
</div>""", unsafe_allow_html=True)
    else:
        lt = res.get("last_trade")
        extra = ""
        if lt:
            extra = (f"<br>Lệnh gần nhất: vào {lt['entry_date']:%d/%m/%Y} @ {_fmt(lt['entry_price'])}"
                     f" → thoát {lt['exit_date']:%d/%m/%Y}, kết quả <b>{lt['pnl_pct']:+.2f}%</b>")
        st.markdown(f"""
<div class="lk-card">
  <div><span class="badge-fib">KHUNG NGÀY</span>
       &nbsp;<span class="lk-ticker" style="font-size:22px">{ticker}</span>
       &nbsp;<span class="val-warn" style="font-size:18px;font-weight:800">⚪ CHỜ TÍN HIỆU</span>
       <span style="color:#aaa"> @ {_fmt(res['last_close'])}</span></div>
  <div class="lk-company">Chưa có lệnh mở. Đường 129 hiện tại: <b>{_fmt(res['lvl3'])}</b>.{extra}</div>
</div>""", unsafe_allow_html=True)

    st.plotly_chart(build_chart(res), use_container_width=True)
    msg = f"Nến cuối {res['last_date']:%d/%m/%Y}"
    if fresh.get("is_stale"):
        msg += f" · ⚠️ dữ liệu trễ {fresh['lag_days']} ngày so với phiên kỳ vọng ({fresh['expected_date']:%d/%m/%Y})"
    st.caption(msg + " · Tín hiệu TƯ VẤN chỉ để tham khảo.")


# ==========================================================
# 4. GIAO DIỆN TAB
# ==========================================================
def render_tin_hieu_ngay_tab(tickers):
    st.markdown("""
    <div class="sb-header"><div class="sb-title">🕯️ Tín hiệu khuyến nghị — Khung ngày</div>
    <div class="sb-sub">Điểm vào / điểm ra theo 3 tầng, dựa trên nến ngày đã đóng cửa</div></div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️ Tham số & luật", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        p_line = c1.number_input("Chu kỳ đường dài", 30, 300, 129, 1)
        vol_mult = c2.number_input("Vol ≥ x MA20", 0.5, 5.0, 1.2, 0.1)
        p_break = c3.number_input("Vượt đỉnh N phiên", 5, 100, 20, 1)
        p_swing = c4.number_input("Đáy ngắn hạn (phiên)", 3, 20, 5, 1)
        st.markdown(
            "**Vào:** nến tăng, đóng cửa trên đường dài, Volume ≥ hệ số × MA20 và vượt đỉnh đóng cửa N phiên. "
            "**Ra:** tầng 1 (30%) thủng đáy ngắn hạn · tầng 2 (30%) thủng chân nến vào · "
            "tầng 3 (40%) thủng đường dài — đều xét theo giá đóng cửa.")

    extra = st.text_input("Thêm mã (cách nhau bằng dấu phẩy)", "", placeholder="VPB, ACB")
    universe = list(dict.fromkeys(
        [t.strip().upper() for t in list(tickers) + extra.split(",") if t and t.strip()]))

    col_a, col_b = st.columns([1, 3])
    if col_a.button("🔄 Quét lại", use_container_width=True):
        scan_signals.clear()
    only_buy = col_b.checkbox("Chỉ hiện mã đang BUY", value=True)

    with st.spinner(f"Đang phân tích {len(universe)} mã..."):
        rows = scan_signals(tuple(universe), int(p_line), float(vol_mult), int(p_break), int(p_swing))

    scan_df = pd.DataFrame(rows)
    if scan_df.empty:
        st.warning("Chưa có dữ liệu.")
        return
    n_buy = int((scan_df["Trạng thái"] == "ĐANG BUY").sum())
    n_err = int(scan_df["Trạng thái"].isin(["Thiếu dữ liệu", "Lỗi dữ liệu"]).sum())
    st.caption(f"📊 {len(scan_df)} mã · 🟢 {n_buy} đang BUY · ⚠️ {n_err} mã thiếu/lỗi dữ liệu")

    shown = scan_df[scan_df["Trạng thái"] == "ĐANG BUY"] if only_buy else scan_df
    if "Số phiên" in shown.columns:
        shown = shown.sort_values("Số phiên", na_position="last")
    st.dataframe(shown, use_container_width=True, hide_index=True)

    options = shown["Mã"].tolist() or universe
    pick = st.selectbox("Xem chi tiết mã", options)
    df = get_stock_data(pick, days_back=400)
    res = analyze_signal(df, p_line=int(p_line), vol_mult=float(vol_mult),
                         p_break=int(p_break), p_swing=int(p_swing))
    if res is None:
        st.info(f"{pick}: chưa đủ dữ liệu (cần > {int(p_line) + 5} phiên).")
        return
    render_card(pick, res)
