"""
tab1_market.py - TAB 1: Thị Trường (dữ liệu trực tiếp từ TCBS).

Dùng trong main.py:
    from tab1_market import render_tab_market
    with tab_market:
        render_tab_market()
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tcbs_client import call_tools, TcbsError

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
GREEN, RED, AMBER, PURPLE, TEXT = "#34d399", "#f87171", "#fbbf24", "#a394d4", "#dcd6ec"


# ---------------------------------------------------------------- tải dữ liệu
@st.cache_data(ttl=60, show_spinner=False)
def load_market(exchange: str):
    """1 lần kết nối, 4 tool TCBS. Cache 60s -> gần real-time mà không spam API."""
    args = {"exchange": exchange, "industry": "ALL"}
    idx, breadth, foreign, leader = call_tools([
        ("tcinvest-getIndustryIndex", args),
        ("tcinvest-getMarketBreadth", args),
        ("tcinvest-getMarketForeignVal", args),
        ("tcinvest-getMarketLeader", args),
    ])
    return {"index": idx, "breadth": breadth, "foreign": foreign, "leader": leader,
            "fetched_at": datetime.now(VN_TZ)}


def _ts(s):
    """'02/10/26' hoặc '02/10/26 14:24' -> Timestamp."""
    s = str(s).strip()
    return pd.to_datetime(s, format="%d/%m/%y %H:%M" if " " in s else "%d/%m/%y", errors="coerce")


def _index_df(raw):
    df = pd.DataFrame(raw.get("data", []))
    if df.empty:
        return df
    df["time"] = df["s"].map(_ts)
    df = df.dropna(subset=["time"]).rename(columns={"i": "close", "v": "volume"})
    df["date"] = df["time"].dt.normalize()
    return df.sort_values("time").reset_index(drop=True)


def _breadth_df(raw):
    df = pd.DataFrame(raw.get("b", []))
    if df.empty:
        return df
    df["time"] = df["t"].map(_ts)
    return df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)


def _foreign_df(raw):
    df = pd.DataFrame(raw.get("data", []))
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["t"], errors="coerce")
    df["ty"] = pd.to_numeric(df["v"], errors="coerce") / 1e9  # VND -> tỷ
    return df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)


def _layout(fig, height):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=36, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=TEXT), legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
    return fig


def _err(raw, name):
    if "_error" in raw:
        st.warning(f"⚠️ {name}: {raw['_error']}")
        return True
    return False


# ---------------------------------------------------------------- giao diện
def render_tab_market():
    c_title, c_sel, c_btn = st.columns([3, 2, 1])
    with c_title:
        st.subheader("🌟 TỔNG QUAN THỊ TRƯỜNG REAL-TIME")
    with c_sel:
        exchange = st.radio("Thị trường", ["HOSE", "HNX", "UPCOM", "VN30"], horizontal=True,
                            key="t1_exchange", label_visibility="collapsed")
    with c_btn:
        if st.button("🔄 CẬP NHẬT DỮ LIỆU", type="primary", use_container_width=True, key="t1_refresh"):
            load_market.clear()
            st.rerun()
    st.divider()

    try:
        with st.spinner("Đang lấy dữ liệu trực tiếp từ TCBS..."):
            data = load_market(exchange)
    except TcbsError as e:
        st.error(f"🚨 {e}")
        return

    # ---- Chỉ số + thanh khoản
    if _err(data["index"], "Chỉ số"):
        return
    df = _index_df(data["index"])
    if len(df) < 2:
        st.warning("⚠️ TCBS chưa trả đủ dữ liệu chỉ số. Thử lại sau ít phút.")
        return

    last, prev = df.iloc[-1], df.iloc[-2]
    live = last["time"] != last["date"]  # có giờ phút -> phiên đang chạy
    chg, pct = last["close"] - prev["close"], (last["close"] / prev["close"] - 1) * 100
    vol_chg = last["volume"] - prev["volume"]

    m1, m2, m3 = st.columns(3)
    m1.metric(f"📊 Chỉ số {exchange if exchange != 'HOSE' else 'VN-INDEX'}",
              f"{last['close']:,.2f} đ", f"{chg:+,.2f} đ ({pct:+.2f}%)")
    m2.metric("💰 Thanh khoản " + ("Hôm Nay (đang khớp)" if live else "phiên gần nhất"),
              f"{last['volume']:,.0f} CP", f"{vol_chg:+,.0f} CP so với phiên trước")
    m3.metric("⏳ Thanh khoản phiên trước (EOD)", f"{prev['volume']:,.0f} CP")

    today_vn = datetime.now(VN_TZ).date()
    stamp = last["time"].strftime("%H:%M %d/%m/%Y") if live else last["time"].strftime("%d/%m/%Y")
    if last["date"].date() == today_vn:
        st.info(f"🕒 Dữ liệu TCBS của phiên **{today_vn:%d/%m/%Y}** · cập nhật tới **{stamp}**"
                f" · tải lúc {data['fetched_at']:%H:%M:%S}")
    else:
        st.warning(f"📅 Hôm nay {today_vn:%d/%m/%Y} chưa có phiên mới (cuối tuần/nghỉ lễ/chưa mở cửa). "
                   f"Đang hiển thị phiên **{stamp}**.")

    # ---- Biểu đồ chỉ số + volume 60 phiên
    d = df.tail(60)
    colors = [PURPLE] * (len(d) - 1) + [GREEN if live else PURPLE]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["time"], y=d["close"], name="Chỉ số", line=dict(color=PURPLE, width=2)))
    fig.add_trace(go.Bar(x=d["time"], y=d["volume"], name="Khối lượng", marker_color=colors,
                         opacity=0.45, yaxis="y2"))
    fig.update_layout(
        title=f"Diễn biến {exchange} · 60 phiên gần nhất",
        yaxis=dict(title="Điểm"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, showticklabels=False,
                    range=[0, d["volume"].max() * 4]),
        xaxis_rangeslider_visible=False, dragmode="pan")
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    st.plotly_chart(_layout(fig, 400), use_container_width=True)
    st.caption("🟣 Phiên đã đóng · 🟢 Phiên hôm nay (đang cập nhật). "
               "TCBS không có dữ liệu theo phút nên biểu đồ theo từng phiên.")

    # ---- Độ rộng thị trường + khối ngoại
    col_a, col_b = st.columns(2)
    with col_a:
        if not _err(data["breadth"], "Độ rộng thị trường"):
            b = _breadth_df(data["breadth"])
            if not b.empty:
                t = b.iloc[-1]
                st.markdown(f"**Độ rộng {exchange}:** 🟢 {int(t['a'])} tăng · 🔴 {int(t['d'])} giảm · "
                            f"🟡 {int(t['s'])} đứng")
                bb = b.tail(20)
                xs = bb["time"].dt.strftime("%d/%m")
                fb = go.Figure()
                fb.add_trace(go.Bar(x=xs, y=bb["a"], name="Tăng", marker_color=GREEN))
                fb.add_trace(go.Bar(x=xs, y=bb["s"], name="Đứng", marker_color=AMBER))
                fb.add_trace(go.Bar(x=xs, y=bb["d"], name="Giảm", marker_color=RED))
                fb.update_layout(barmode="stack", title="Số mã tăng/giảm · 20 phiên")
                fb.update_xaxes(type="category")
                st.plotly_chart(_layout(fb, 320), use_container_width=True)
    with col_b:
        if not _err(data["foreign"], "Khối ngoại"):
            f = _foreign_df(data["foreign"])
            if not f.empty:
                t = f.iloc[-1]
                st.markdown(f"**Khối ngoại {exchange} ({t['time']:%d/%m}):** "
                            f"{'🟢 mua ròng' if t['ty'] >= 0 else '🔴 bán ròng'} {abs(t['ty']):,.0f} tỷ")
                ff = f.tail(20)
                fg = go.Figure(go.Bar(x=ff["time"].dt.strftime("%d/%m"), y=ff["ty"],
                                      marker_color=[GREEN if v >= 0 else RED for v in ff["ty"]]))
                fg.update_layout(title="Giá trị mua/bán ròng · 20 phiên (tỷ đồng)")
                fg.update_xaxes(type="category")
                st.plotly_chart(_layout(fg, 320), use_container_width=True)

    # ---- Nhóm dẫn dắt chỉ số
    if not _err(data["leader"], "Nhóm dẫn dắt"):
        lead = data["leader"]
        inc, dec = pd.DataFrame(lead.get("listInc", [])), pd.DataFrame(lead.get("listDesc", []))
        if not inc.empty or not dec.empty:
            st.markdown(f"**Mã tác động mạnh nhất tới {exchange}** (điểm đóng góp, 1 tháng gần nhất"
                        f"{' · ' + str(lead['time']) if lead.get('time') else ''})")
            la, lb = st.columns(2)
            for col, frame, color, title in ((la, inc, GREEN, "Kéo chỉ số lên"), (lb, dec, RED, "Kéo chỉ số xuống")):
                with col:
                    if frame.empty:
                        continue
                    frame = frame.sort_values("s", ascending=(color == GREEN)).tail(10)
                    fl = go.Figure(go.Bar(x=frame["s"], y=frame["ticker"], orientation="h", marker_color=color))
                    fl.update_layout(title=title)
                    st.plotly_chart(_layout(fl, 320), use_container_width=True)
