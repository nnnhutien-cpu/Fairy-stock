"""
tab_watchlist.py — Tab Danh mục, phần "Mã tiềm năng hôm nay".

Quét danh sách mã ưu tiên bằng đúng bộ luật của tab Khuyến Nghị
(_compute_recommendation_data), giữ lại các mã đang có tín hiệu MUA,
xếp hạng và chỉ hiện 3–5 mã mạnh nhất dưới dạng thẻ xếp hàng dọc.
"""
import concurrent.futures
from datetime import datetime

import json
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data_loader import get_stock_data
from tab_khuyen_nghi import _compute_recommendation_data

# Thứ tự ưu tiên tín hiệu mua: (từ khoá trong khuyến nghị, nhãn ngắn, tỷ trọng, điểm)
_BUY_TIERS = [
    ("MUA MẠNH", "Mua mạnh", 30, 5),
    ("MUA (20%)", "Mua", 20, 4),
    ("BẮT ĐÁY", "Bắt đáy", 10, 3),
    ("THĂM DÒ (10%)", "Thăm dò", 10, 2),
    ("THĂM DÒ", "Thăm dò", 5, 1),
]

_CSS = """
<style>
.pk-bar{ display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin: 2px 0 12px; }
.pk-h{ font-weight:800; color:var(--ink); font-size:1.02rem; }
.pk-t{ font-size:.78rem; color:var(--muted); }
.pk-empty{ border:1px dashed #3a2f66; border-radius:16px; padding:22px; text-align:center; color:var(--muted); font-size:.88rem; }
iframe[title="st.iframe"], [data-testid="stIFrame"]{ border:0; }
</style>
"""


def _buy_tier(kn: str):
    k = kn.upper()
    if "MUA" not in k and "BẮT ĐÁY" not in k:
        return None
    for key, label, pct, pts in _BUY_TIERS:
        if key in k:
            return label, pct, pts
    return None


@st.cache_data(ttl=900, show_spinner=False)
def _analyze(ticker, p_tenkan, p_kijun, p_senkou_b, p_shift):
    try:
        df = get_stock_data(ticker, days_back=400)
        if df is None or df.empty or len(df) < 140:
            return None
        r = _compute_recommendation_data(df, ticker, p_tenkan, p_kijun, p_senkou_b, p_shift)
        tier = _buy_tier(r["khuyen_nghi"])
        if tier is None:
            return {"buy": False}
        label, pct, pts = tier
        rsi = float(r["rsi"]) if pd.notna(r["rsi"]) else None
        # Điểm xếp hạng: bậc tín hiệu là chính; cùng bậc thì ưu tiên xu hướng tăng, giá gần Knife129, vol tốt
        score = (pts * 100 + {"TANG": 20, "SIDEWAY": 10}.get(r["xu_huong"], 0)
                 - min(abs(float(r["pct_vs_129"])), 30) + min(float(r["v_ratio"]), 3) * 5)
        return {
            "buy": True, "ticker": ticker, "label": label, "pct": pct, "score": score,
            "trend": r["xu_huong"], "close": float(r["close"]), "rsi": rsi,
            "pct_vs_129": float(r["pct_vs_129"]), "v_ratio": float(r["v_ratio"]),
            "mo_ta": r["mo_ta"], "khuyen_nghi": r["khuyen_nghi"], "ly_do": list(r["ly_do"]),
            "series": _series(r["df"]),
        }
    except Exception:
        return None


def _series(d, n=160):
    """Dữ liệu vẽ biểu đồ, gửi thẳng xuống trình duyệt (bấm mã là vẽ ngay, không gọi lại server)."""
    d = d.tail(n)
    tcol = "time" if "time" in d.columns else None
    times = (pd.to_datetime(d[tcol]) if tcol else pd.to_datetime(d.index)).dt.strftime("%Y-%m-%d") \
        if tcol else pd.to_datetime(d.index).strftime("%Y-%m-%d")

    def col(c):
        return [None if pd.isna(v) else round(float(v), 2) for v in d[c]] if c in d.columns else []

    return {"t": list(times), "o": col("open"), "h": col("high"), "l": col("low"), "c": col("close"),
            "v": [0 if pd.isna(v) else float(v) for v in d["volume"]],
            "k129": col("knife129"), "k65": col("knife65"), "k17": col("kijun17")}


def _scan(tickers, params):
    hits, ok = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(lambda t: _analyze(t, *params), tickers):
            if r:
                ok += 1
                if r["buy"]:
                    hits.append(r)
    return sorted(hits, key=lambda x: x["score"], reverse=True), ok


PANEL_H = 460
_TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pick_panel.html")


@st.cache_data(show_spinner=False)
def _template(mtime):
    with open(_TPL, encoding="utf-8") as f:
        return f.read()


def _panel_html(picks):
    """Danh sách mã + biểu đồ trong 1 khung: bấm mã đổi biểu đồ ngay trên trình duyệt."""
    data = json.dumps(picks, ensure_ascii=False).replace("</", "<\\/")
    return _template(os.path.getmtime(_TPL)).replace("__H__", str(PANEL_H)).replace("__DATA__", data)


def render_watchlist(universe, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    st.markdown(_CSS, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([4, 1.3, 1], vertical_alignment="center")
    with c2:
        n_show = st.segmented_control("Số mã", [3, 4, 5], default=5, key="pk_n",
                                      format_func=lambda x: f"{x} mã", label_visibility="collapsed") or 5
    with c3:
        if st.button("🔄 Lọc lại", width="stretch", key="pk_refresh"):
            _analyze.clear()
            st.session_state.pop("pk_time", None)

    params = (int(p_tenkan), int(p_kijun), int(p_senkou_b), int(p_shift))
    with st.spinner(f"Đang lọc {len(universe)} mã…"):
        hits, n_ok = _scan(list(universe), params)
    st.session_state.setdefault("pk_time", datetime.now().strftime("%H:%M · %d/%m/%Y"))

    with c1:
        st.markdown(
            f'<div class="pk-bar"><div><div class="pk-h">✨ Mã tiềm năng hôm nay</div>'
            f'<div class="pk-t">Lọc từ {n_ok}/{len(universe)} mã thanh khoản cao · {len(hits)} mã có tín hiệu mua · '
            f'lọc lúc {st.session_state["pk_time"]}</div></div></div>',
            unsafe_allow_html=True,
        )

    picks = hits[:n_show]
    if picks:
        components.html(_panel_html(picks), height=PANEL_H + 8, scrolling=False)
        st.caption("Bấm vào mã để xem biểu đồ ngay (không cần tải lại). Lăn chuột để phóng to, kéo để xem quá khứ. "
                   "Số % là tỷ trọng vốn gợi ý theo bộ luật tab Khuyến Nghị — chỉ mang tính tham khảo, "
                   "không phải khuyến nghị đầu tư.")
    elif n_ok == 0:
        st.warning("Chưa lấy được dữ liệu giá. Bấm 🔄 Lọc lại sau ít phút.")
    else:
        st.markdown('<div class="pk-empty">Hôm nay chưa có mã nào đạt tín hiệu mua. '
                    'Đứng ngoài cũng là một vị thế 🌙</div>', unsafe_allow_html=True)
