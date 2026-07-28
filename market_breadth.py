# market_breadth.py
import streamlit as st
import requests

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/nnnhutien-cpu/Fairy-stock/main"

@st.cache_data(ttl=1800, show_spinner=False)
def get_market_breadth() -> dict | None:
    try:
        url = f"{GITHUB_RAW_BASE}/breadth_latest.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None

def render_breadth_panel(breadth: dict):
    if breadth is None:
        st.info("⏳ Chưa có dữ liệu breadth. GitHub Actions chưa chạy lần nào.")
        return

    import streamlit as st
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📊 A/D%", f"{breadth.get('ad_pct', 0):.1f}%")
    c2.metric("📈 %>MA20", f"{breadth.get('pct_above_ma20', 0):.1f}%")
    c3.metric("📉 %>MA50", f"{breadth.get('pct_above_ma50', 0):.1f}%")
    c4.metric("🎯 Breadth Score", f"{breadth.get('breadth_score', 0):+d}")

    note = breadth.get("momentum_note")
    if note:
        st.info(note)

    st.caption(f"🕒 Cập nhật: {breadth.get('updated_at', '—')} | {breadth.get('n_total', 0)} mã hợp lệ / {breadth.get('n_tickers_target', 0)} mã target")
