"""
tab_market.py — Tab "🌟 Thị Trường" (bản thiết kế lại).

Trình bày theo thứ tự nhà đầu tư cần ra quyết định:
  1. KẾT LUẬN     : pha thị trường + hành động + tỷ trọng gợi ý + 1 câu lý do
  2. CHỈ SỐ NHANH : VN-Index, khoảng cách tới đỉnh, RSI, ngày phân phối, % mã trên MA50
  3. KỊCH BẢN     : mốc giá nào thì nâng / hạ tỷ trọng
  4. CHI TIẾT     : Xu hướng · Trong phiên · Độ rộng · Nhóm chỉ số · Định giá · Bảng điểm

Toàn bộ logic tính toán nằm ở market_insights.py (test được không cần streamlit).
"""
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import market_insights as mi
import ui_kit
import valuation
from data_loader import get_index_data, get_intraday_vnindex
from market_breadth import _fetch_breadth_raw, breadth_freshness, get_market_breadth
from market_fallback import fetch_tcbs_vnindex

# ── Bảng màu biểu đồ (đã kiểm tra tương phản + mù màu trên nền tối #0f0a1f) ──
INK, MUTED, GRID, VOL = ui_kit.INK, ui_kit.MUTED, ui_kit.GRID, ui_kit.VOL
MA_STYLE = {"ma20": (ui_kit.SERIES[0], "dot"), "ma50": (ui_kit.SERIES[1], "dash"), "ma200": (ui_kit.SERIES[2], "solid")}
GOOD, BAD = ui_kit.UP, ui_kit.DOWN
IDX_COLORS = {"VNINDEX": INK, "VN30": ui_kit.SERIES[0], "HNXINDEX": ui_kit.SERIES[1], "UPCOM": ui_kit.SERIES[2]}
_ST_COLOR = {"success": "green", "info": "blue", "warning": "orange", "danger": "red", "gray": "gray"}


def _header(title, sub=""):
    ui_kit.page_header(title, sub)


def _fmt(v, spec, dash="—"):
    v = mi._f(v)
    return format(v, spec) if v is not None else dash


def _layout(fig, height):
    return ui_kit.style_fig(fig, height, dates=False)


def _vn_now():
    return pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None)


def _in_session():
    n = _vn_now()
    return n.weekday() < 5 and "09:00" <= n.strftime("%H:%M") <= "15:05"


# ════════════════════════════════════════════════════════════════════
# NẠP DỮ LIỆU (lỗi thì ném ngoại lệ -> streamlit KHÔNG cache kết quả lỗi)
# ════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=900, show_spinner=False)
def load_index(symbol, days=420):
    d = mi.normalize_daily(get_index_data(symbol, days_back=days))
    if (d is None or len(d) < 60) and symbol == "VNINDEX":
        d = mi.normalize_daily(fetch_tcbs_vnindex(250))
    if d is None or len(d) < 30:
        raise RuntimeError(f"Không lấy được giá ngày {symbol}")
    return d


def _try_index(symbol, days=420):
    try:
        return load_index(symbol, days)
    except Exception:
        return None


def _load_pe(price):
    try:
        pe_now = valuation.get_current_pe(price)
        hist = valuation.get_pe_history(years=20)
        return valuation.pe_stats(hist, pe_now), hist, valuation.get_current_pe_source()
    except Exception:
        return None, None, None


def _clear_caches():
    for fn in (load_index, get_index_data, get_intraday_vnindex, _fetch_breadth_raw):
        try:
            fn.clear()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
# 1–3. KẾT LUẬN · CHỈ SỐ NHANH · KỊCH BẢN
# ════════════════════════════════════════════════════════════════════
def _render_verdict(m, regime, sc, bview):
    r_label, r_color, r_desc = mi.REGIMES[regime]
    color = _ST_COLOR.get(sc["color"], "gray")
    with st.container(border=True):
        c1, c2 = st.columns([3, 1.2])
        with c1:
            st.markdown(f":{_ST_COLOR.get(r_color, 'gray')}-background[**{r_label}**]  "
                        f"&nbsp;·&nbsp; phiên {m['date']:%d/%m/%Y}")
            st.markdown(f"### :{color}[{sc['action']}]")
            st.markdown(mi.headline(m, regime, sc, bview))
        with c2:
            st.metric("Tỷ trọng cổ phiếu gợi ý", f"{sc['equity']}%",
                      f"Tổng điểm {sc['total']:+d}", delta_color="off")
            st.progress(sc["equity"] / 100, text=f"Cổ phiếu {sc['equity']}% · Tiền {sc['cash']}%")
        if sc.get("cap") is not None and sc["equity"] == sc["cap"]:
            st.caption(f"🔒 Pha **{r_label.split(' ', 1)[1].lower()}** giới hạn tỷ trọng tối đa {sc['cap']}% "
                       "dù điểm kỹ thuật cao hơn — không chống lại xu hướng chính.")


def _render_kpis(m, bview):
    k = st.columns(5)
    k[0].metric("📊 VN-Index", _fmt(m["price"], ",.2f"),
                f"{m['chg_pct']:+.2f}%" if m.get("chg_pct") is not None else None)
    k[1].metric("🏔️ Từ đỉnh 52 tuần", f"{m['dd_from_high']:.1f}%",
                help=f"Đỉnh {m['high52']:,.0f} ngày {m['high52_date']:%d/%m/%Y}. "
                     "≤ -10% là điều chỉnh, ≤ -20% là thị trường giá xuống.")
    rsi = m.get("rsi")
    k[2].metric("⚡ RSI(14)", _fmt(rsi, ".0f"),
                ("Quá mua" if rsi >= 70 else "Quá bán" if rsi <= 30 else None) if rsi is not None else None,
                delta_color="off")
    nd = m.get("dist_days", 0)
    k[3].metric("🔻 Ngày phân phối", f"{nd}/25",
                "Cảnh báo" if nd >= 5 else None, delta_color="inverse",
                help="Phiên VN-Index giảm ≥ 0,2% với khối lượng cao hơn phiên trước — dấu hiệu tổ chức bán ra. "
                     "Từ 5–6 ngày trong 25 phiên thường đi trước nhịp điều chỉnh. Gần nhất: "
                     + (", ".join(m.get("dist_dates", [])[-6:]) or "không có"))
    if bview and bview.get("pct50") is not None:
        k[4].metric("🌡️ % mã trên MA50", f"{bview['pct50']:.0f}%",
                    None if bview.get("usable") else "chưa đủ tin cậy", delta_color="off",
                    help="Tỷ lệ cổ phiếu HOSE đang giá trên MA50. > 60% là khoẻ, < 30% là yếu diện rộng.")
    else:
        k[4].metric("🌡️ % mã trên MA50", "—")


def _render_watch(m, regime):
    items = mi.watch_levels(m, regime)
    if not items:
        return
    st.markdown("##### 🎯 Kịch bản hành động")
    icon = {"up": "🟢", "down": "🔴", "info": "🔵"}
    for kind, text in items:
        st.markdown(f"{icon.get(kind, '•')} {text}")


# ════════════════════════════════════════════════════════════════════
# 4a. XU HƯỚNG
# ════════════════════════════════════════════════════════════════════
def _render_trend(m):
    ch = m["_chart"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.76, 0.24], vertical_spacing=0.04)
    fig.add_trace(go.Scatter(x=ch["time"], y=ch["close"], name="VN-Index",
                             line=dict(color=INK, width=2)), row=1, col=1)
    for key, (col, dash) in MA_STYLE.items():
        if ch[key].notna().any():
            fig.add_trace(go.Scatter(x=ch["time"], y=ch[key], name=key.upper(),
                                     line=dict(color=col, width=1.6, dash=dash)), row=1, col=1)
    # Khối lượng: ngày phân phối tô đỏ để thấy ngay áp lực bán dồn dập
    chg = ch["close"].pct_change() * 100
    is_dist = (chg <= mi.DIST_DROP_PCT) & (ch["volume"] > ch["volume"].shift(1))
    fig.add_trace(go.Bar(x=ch["time"], y=ch["volume"] / 1e6, name="KL (triệu CP)",
                         marker_color=[BAD if x else VOL for x in is_dist], marker_line_width=0,
                         hovertemplate="%{y:,.0f}M CP<extra></extra>", showlegend=False), row=2, col=1)
    if m.get("ftd"):
        f = m["ftd"]
        fig.add_annotation(x=f["date"], y=float(ch.loc[ch["time"] == f["date"], "close"].iloc[0]),
                           text="FTD", showarrow=True, arrowhead=2, font=dict(color=GOOD), row=1, col=1)
    _layout(fig, 460)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(title_text="KL (M)", title_font=dict(size=10), row=2, col=1)
    ui_kit.plot(fig)
    st.caption("Cột khối lượng **đỏ** = ngày phân phối (giảm ≥ 0,2% với khối lượng tăng). "
               "MA20 chấm · MA50 gạch · MA200 liền.")

    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.markdown("##### 📍 Mốc giá quan trọng")
        lv = mi.key_levels(m)
        if not lv.empty:
            st.dataframe(lv, hide_index=True, width="stretch", column_config={
                "Điểm": st.column_config.NumberColumn(format="%.1f"),
                "Cách giá": st.column_config.NumberColumn(format="%+.1f%%"),
            })
    with c2:
        st.markdown("##### 🧭 Đọc nhanh")
        st.markdown(f"- **Pha:** {mi.REGIMES[mi.classify_regime(m)][2]}")
        st.markdown(f"- **Hiệu suất:** 1 tuần {_fmt(m.get('roc5'), '+.1f')}% · 1 tháng {_fmt(m.get('roc20'), '+.1f')}% "
                    f"· 3 tháng {_fmt(m.get('roc60'), '+.1f')}%")
        st.markdown(f"- **Biên dao động TB (ATR14):** {_fmt(m.get('atr_pct'), '.2f')}%/phiên "
                    f"(≈ {_fmt((m.get('atr_pct') or 0) * m['price'] / 100, ',.0f')} điểm)")
        hist_dir = "cải thiện" if (m.get("macd_hist") or 0) > (m.get("macd_hist_prev") or 0) else "xấu đi"
        st.markdown(f"- **MACD:** {_fmt(m.get('macd'), '+.1f')} / Signal {_fmt(m.get('macd_signal'), '+.1f')} "
                    f"— histogram đang {hist_dir}")
        if m.get("ftd"):
            f = m["ftd"]
            st.success(f"✅ Follow-Through Day ngày {f['date']:%d/%m} (+{f['gain']:.1f}%) sau đáy "
                       f"{f['low']:,.0f} ({f['drawdown']:.1f}% từ đỉnh) — tín hiệu xác nhận đáy.")


# ════════════════════════════════════════════════════════════════════
# 4b. TRONG PHIÊN (tự làm mới riêng phần này)
# ════════════════════════════════════════════════════════════════════
def _prepare_intraday(raw):
    if raw is None or raw.empty or "time" not in raw.columns:
        return None, None
    df = raw.copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df["close"] = pd.to_numeric(df.get("close"), errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    df["hm"] = df["time"].dt.strftime("%H:%M")
    df["date"] = df["time"].dt.date
    df = df[(df["hm"] >= "09:00") & (df["hm"] <= "15:00")]
    dates = sorted(df["date"].unique())
    if not dates:
        return None, None
    today = df[df["date"] == dates[-1]].copy()
    yday = df[df["date"] == dates[-2]].copy() if len(dates) >= 2 else None
    return today, yday


def _render_intraday_body(ref_close):
    today, yday = _prepare_intraday(get_intraday_vnindex())
    if today is None or today.empty:
        st.info("📡 Chưa có dữ liệu trong phiên (ngoài giờ giao dịch hoặc nguồn dữ liệu 1 phút đang lỗi). "
                "Các phần phân tích khác dùng giá đóng cửa và vẫn chính xác.")
        return
    today["cum"] = today["volume"].cumsum()
    last_hm = today["hm"].iloc[-1]
    last_px = float(today["close"].iloc[-1])
    same = None
    if yday is not None and not yday.empty:
        yday["cum"] = yday["volume"].cumsum()
        s = yday.loc[yday["hm"] <= last_hm, "cum"]
        same = float(s.iloc[-1]) if len(s) else None

    c = st.columns(3)
    base = mi._f(ref_close)
    c[0].metric(f"VN-Index lúc {last_hm}", f"{last_px:,.2f}",
                f"{(last_px / base - 1) * 100:+.2f}%" if base else None)
    c[1].metric("KL lũy kế", f"{today['cum'].iloc[-1] / 1e6:,.0f}M CP",
                f"{(today['cum'].iloc[-1] / same - 1) * 100:+.0f}% so với cùng giờ phiên trước" if same else None)
    c[2].metric("KL cả phiên trước", f"{yday['cum'].iloc[-1] / 1e6:,.0f}M CP" if same else "—")

    fig = go.Figure()
    if yday is not None and not yday.empty:
        fig.add_trace(go.Scatter(x=yday["hm"], y=yday["cum"] / 1e6, name="Phiên trước",
                                 line=dict(color=MUTED, width=1.6, dash="dot")))
    fig.add_trace(go.Scatter(x=today["hm"], y=today["cum"] / 1e6, name=f"Hôm nay (đến {last_hm})",
                             line=dict(color=INK, width=2.2)))
    _layout(fig, 300)
    fig.update_xaxes(type="category", nticks=10)
    fig.update_yaxes(title_text="KL lũy kế (triệu CP)", title_font=dict(size=10))
    ui_kit.plot(fig)
    if same:
        ratio = today["cum"].iloc[-1] / same
        chg_now = (last_px / base - 1) * 100 if base else 0
        if ratio >= 1.2 and chg_now > 0:
            st.success("💚 Thanh khoản cao hơn phiên trước và chỉ số tăng — dòng tiền chủ động mua.")
        elif ratio >= 1.2 and chg_now < 0:
            st.error("🔻 Thanh khoản cao hơn phiên trước nhưng chỉ số giảm — áp lực bán chủ động.")
        elif ratio <= 0.8:
            st.info("💤 Thanh khoản thấp hơn phiên trước — thị trường thận trọng, biến động giá ít tin cậy.")


# ════════════════════════════════════════════════════════════════════
# 4c. ĐỘ RỘNG
# ════════════════════════════════════════════════════════════════════
def _render_breadth(breadth, bview):
    if not breadth or not bview:
        st.info("⏳ Chưa đọc được breadth.json. Vào **GitHub → Actions → Scan Breadth HOSE → Run workflow** để quét.")
        return
    fresh = breadth_freshness(breadth)
    st.caption(f"🕒 Bot quét lúc **{breadth.get('updated_at')}** · phiên **{bview.get('data_date')}** · "
               f"**{bview.get('n') or 0} mã** HOSE · cập nhật 1 lần/ngày sau đóng cửa")
    if (bview.get("n") or 0) < 100:
        st.warning(f"⚠️ Dữ liệu chỉ gồm {bview.get('n')} mã (cần ~380 mã HOSE) nên **chưa đưa vào chấm điểm**. "
                   "Bot sẽ quét đủ khi repo có tickers.json.")
    elif fresh.get("is_stale") or fresh.get("data_stale"):
        st.warning(f"⚠️ Dữ liệu độ rộng cũ (trễ {fresh.get('lag_days')} ngày) — kiểm tra workflow Scan Breadth HOSE.")

    c = st.columns(4)
    c[0].metric("% mã tăng (phiên)", _fmt(bview.get("ad_pct"), ".0f") + "%",
                f"{bview.get('advance')} tăng / {bview.get('decline')} giảm", delta_color="off")
    c[1].metric("% trên MA20", _fmt(bview.get("pct20"), ".0f") + "%")
    c[2].metric("% trên MA50", _fmt(bview.get("pct50"), ".0f") + "%")
    c[3].metric("Tăng/giảm 10 phiên", _fmt(bview.get("ad10"), ".2f"),
                help="Tổng số mã tăng / tổng số mã giảm trong 10 phiên. > 1,2 là bên mua lan toả, < 0,8 là bên bán lan toả.")

    h = bview.get("hist")
    if h is not None and not h.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.06)
        fig.add_trace(go.Bar(x=h["date"], y=h["adv"], name="Số mã tăng", marker_color=GOOD,
                             marker_line_width=0), row=1, col=1)
        fig.add_trace(go.Bar(x=h["date"], y=-h["dec"], name="Số mã giảm", marker_color=BAD,
                             marker_line_width=0, customdata=h["dec"],
                             hovertemplate="%{customdata} mã giảm<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=h["date"], y=h["ad_line"], name="Đường A/D tích luỹ",
                                 line=dict(color=INK, width=2)), row=2, col=1)
        _layout(fig, 360)
        fig.update_layout(barmode="relative", bargap=0.25)
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        ui_kit.plot(fig)
        st.caption("Đường A/D đi lên = số mã tăng liên tục áp đảo (sức khoẻ thật của thị trường), "
                   "kể cả khi VN-Index đi ngang.")
    if bview.get("divergence"):
        kind, text = bview["divergence"]
        (st.warning if kind == "bearish" else st.success)(text)
    if breadth.get("momentum_note"):
        st.info(breadth["momentum_note"])


# ════════════════════════════════════════════════════════════════════
# 4d. NHÓM CHỈ SỐ
# ════════════════════════════════════════════════════════════════════
def _render_groups(vni_df):
    dfs = {"VNINDEX": vni_df}
    for sym in ("VN30", "HNXINDEX", "UPCOM"):
        d = _try_index(sym, 200)
        if d is not None:
            dfs[sym] = d
    rp = mi.relative_perf(dfs)
    if rp.empty:
        st.info("Chưa tải được dữ liệu các chỉ số.")
        return
    note = mi.rotation_insight(rp)
    if note:
        st.markdown(note)
    show = rp.drop(columns=["_sym"])
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        "Điểm": st.column_config.NumberColumn(format="%.2f"),
        **{c: st.column_config.NumberColumn(format="%+.1f%%") for c in ("1 tuần", "1 tháng", "3 tháng")},
    })
    fig = go.Figure()
    for sym, d in dfs.items():
        t = d.tail(61)
        if len(t) < 2:
            continue
        fig.add_trace(go.Scatter(x=t["time"], y=t["close"] / t["close"].iloc[0] * 100,
                                 name=mi.INDEX_LABELS.get(sym, sym),
                                 line=dict(color=IDX_COLORS.get(sym, MUTED), width=2.2 if sym == "VNINDEX" else 1.8)))
    fig.add_hline(y=100, line=dict(color=MUTED, width=1, dash="dot"))
    _layout(fig, 320)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(title_text="Quy về 100 (60 phiên trước)", title_font=dict(size=10))
    ui_kit.plot(fig)
    if len(dfs) < 4:
        st.caption("Một số chỉ số chưa tải được, bảng chỉ hiển thị phần có dữ liệu.")


# ════════════════════════════════════════════════════════════════════
# 4e. ĐỊNH GIÁ
# ════════════════════════════════════════════════════════════════════
def _render_valuation(pe, pe_hist, pe_src):
    if not pe or pe.get("pe_now") is None:
        st.info("⏳ Chưa tải được P/E VN-Index.")
        return
    c = st.columns(4)
    c[0].metric("P/E hiện tại", f"{pe['pe_now']:.1f}x",
                f"{pe['pct_vs_avg']:+.0f}% so với TB" if pe.get("pct_vs_avg") is not None else None,
                delta_color="inverse")
    c[1].metric("TB lịch sử", _fmt(pe.get("mean"), ".1f") + "x")
    c[2].metric("Percentile", _fmt(pe.get("percentile"), ".0f") + "%",
                help="Tỷ lệ số năm trong lịch sử có P/E THẤP hơn hiện tại. < 35% là rẻ, > 65% là đắt.")
    ey = 100 / pe["pe_now"] if pe["pe_now"] else None
    c[3].metric("Lợi suất lợi nhuận (E/P)", _fmt(ey, ".1f") + "%",
                help="= 1 / P/E. So với lãi suất tiết kiệm 12 tháng: E/P cao hơn rõ rệt thì cổ phiếu hấp dẫn hơn gửi tiết kiệm.")
    if pe.get("comment"):
        st.markdown(pe["comment"])
    if pe_hist is not None and not pe_hist.empty:
        fig = go.Figure(go.Scatter(x=pe_hist["date"], y=pe_hist["pe"], name="P/E cuối năm",
                                   mode="lines+markers", line=dict(color=INK, width=2), marker=dict(size=8)))
        fig.add_hline(y=pe["pe_now"], line=dict(color=MA_STYLE["ma20"][0], width=1.6, dash="dash"),
                      annotation_text=f"Hiện tại {pe['pe_now']:.1f}x", annotation_font_color=INK)
        if pe.get("mean"):
            fig.add_hline(y=pe["mean"], line=dict(color=MUTED, width=1, dash="dot"),
                          annotation_text=f"TB {pe['mean']:.1f}x", annotation_position="bottom right",
                          annotation_font_color=MUTED)
        _layout(fig, 280)
        fig.update_layout(showlegend=False)
        ui_kit.plot(fig)
    if pe_src:
        st.caption(f"🔗 Nguồn P/E hiện tại: **{pe_src}** · P/E lịch sử: bảng P/E cuối năm trong valuation.py")


# ════════════════════════════════════════════════════════════════════
# 4f. BẢNG ĐIỂM
# ════════════════════════════════════════════════════════════════════
def _render_scoreboard(sc, regime):
    df = pd.DataFrame(sc["factors"])
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Điểm": st.column_config.NumberColumn(format="%+d"),
        "Ý nghĩa": st.column_config.TextColumn(width="large"),
    })
    by = df.groupby("Nhóm", sort=False)["Điểm"].sum()
    st.markdown("**Tổng theo nhóm:** " + " · ".join(f"{k} {v:+d}" for k, v in by.items())
                + f" → **Tổng {sc['total']:+d}**")
    st.markdown(
        f'<div class="formula-note">Tỷ trọng = 50% + 4% × tổng điểm (làm tròn 10%, giới hạn 10–90%).<br>'
        f'Pha thị trường đặt <b>trần/sàn</b>: xu hướng giảm tối đa 40%, điều chỉnh/hồi phục tối đa 70%, '
        f'xu hướng tăng tối thiểu 40%. Pha hiện tại: <b>{mi.REGIMES[regime][0]}</b>.<br>'
        f'Độ rộng chỉ được tính khi bot quét ≥ 100 mã và dữ liệu không cũ quá 4 ngày.</div>',
        unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# ENTRY
# ════════════════════════════════════════════════════════════════════
def render_market():
    c_title, c_btn, c_auto = st.columns([3, 1, 1])
    with c_title:
        _header("🌟 Tổng quan thị trường", "Pha thị trường · độ rộng · dòng tiền · định giá → tỷ trọng gợi ý")
    with c_btn:
        if st.button("🔄 CẬP NHẬT", type="primary", width="stretch", key="btn_refresh_market"):
            _clear_caches()
            st.rerun()
    with c_auto:
        refresh = st.selectbox("⏱️ Tự làm mới (trong phiên)", [0, 30, 60, 120, 300], index=2,
                               format_func=lambda x: "Tắt" if x == 0 else f"{x}s",
                               key="refresh_interval_select", label_visibility="collapsed")

    with st.spinner("Đang tải dữ liệu thị trường…"):
        vni = _try_index("VNINDEX")
        m = mi.index_metrics(vni) if vni is not None else None
        breadth = None
        try:
            breadth = get_market_breadth()
        except Exception:
            pass

    if m is None:
        st.error("⚠️ Không tải được giá ngày VN-Index từ TCBS / DNSE / Yahoo nên chưa phân tích được. "
                 "Bấm **🔄 CẬP NHẬT** để thử lại sau ít phút.")
        st.markdown("#### 💓 Trong phiên")
        _render_intraday_body(None)
        return

    regime = mi.classify_regime(m)
    bview = mi.breadth_view(breadth, m)
    pe, pe_hist, pe_src = _load_pe(m["price"])
    sc = mi.score_market(m, regime, bview, pe)

    _render_verdict(m, regime, sc, bview)
    _render_kpis(m, bview)
    _render_watch(m, regime)
    if bview and bview.get("divergence"):
        kind, text = bview["divergence"]
        (st.warning if kind == "bearish" else st.success)(text)

    t_trend, t_intra, t_breadth, t_groups, t_val, t_score = st.tabs(
        ["📈 Xu hướng", "💓 Trong phiên", "🏥 Độ rộng", "🔀 Nhóm chỉ số", "💰 Định giá", "🧮 Bảng điểm"])
    with t_trend:
        _render_trend(m)
    with t_intra:
        interval = refresh if _in_session() else 0
        st.caption(f"🔁 Tự làm mới mỗi {interval}s" if interval else "⏸️ Tự làm mới chỉ chạy trong giờ giao dịch")
        # Chỉ phần trong phiên chạy lại theo chu kỳ; phần phân tích ngày không bị tải lại
        prev_close = float(m["_chart"]["close"].iloc[-2]) if m["date"].date() == _vn_now().date() and len(m["_chart"]) > 1 \
            else m["price"]

        def _intra():  # get_intraday_vnindex có ttl=60s nên mỗi lượt làm mới tự lấy dữ liệu mới
            _render_intraday_body(prev_close)

        st.fragment(_intra, run_every=(interval or None))()
    with t_breadth:
        _render_breadth(breadth, bview)
    with t_groups:
        _render_groups(vni)
    with t_val:
        _render_valuation(pe, pe_hist, pe_src)
    with t_score:
        _render_scoreboard(sc, regime)

    st.caption("⚠️ Phân tích tự động từ dữ liệu kỹ thuật, độ rộng và định giá — chỉ mang tính tham khảo, "
               "không phải khuyến nghị đầu tư.")
