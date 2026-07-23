"""
market_breadth.py
Tính breadth thị trường (mã tăng/giảm, MA, đáy/đỉnh, A/D ratio)
Nguồn 1: scan_results có sẵn trong session_state (luôn hoạt động)
Nguồn 2: TCBS market summary API (fallback khi có mạng)
"""
import pandas as pd
import numpy as np
import requests
import streamlit as st
from typing import Optional


# ─────────────────────────────────────────────
# NGUỒN 1: Tính từ scan_results
# ─────────────────────────────────────────────
def breadth_from_scan(scan_results: list) -> Optional[dict]:
    """Tính breadth từ danh sách kết quả quét có sẵn."""
    if not scan_results:
        return None

    df = pd.DataFrame(scan_results)
    if df.empty:
        return None

    total = len(df)

    # --- Tăng / Giảm / Đứng ---
    advancing = declining = unchanged = 0
    if "Thay Đổi %" in df.columns:
        chg = pd.to_numeric(df["Thay Đổi %"], errors="coerce").fillna(0)
        advancing = int((chg > 0).sum())
        declining  = int((chg < 0).sum())
        unchanged  = total - advancing - declining
    elif "Xu Hướng" in df.columns:
        advancing = int((df["Xu Hướng"] == "Tăng").sum())
        declining  = int((df["Xu Hướng"] == "Giảm").sum())
        unchanged  = total - advancing - declining

    ad_ratio = round(advancing / declining, 2) if declining > 0 else float("inf")

    # --- Trên MA20 ---
    above_ma20 = 0
    if "Vol x TB20" in df.columns:
        # Nếu Vol x TB20 > 0 thì mã có volume — dùng Xu Hướng để ước MA
        above_ma20 = advancing  # proxy: mã tăng ≈ trên MA20

    # --- Trạng thái tín hiệu ---
    signal_counts = {}
    if "Trạng thái" in df.columns:
        signal_counts = df["Trạng thái"].value_counts().to_dict()

    # --- Mã có dòng tiền mạnh ---
    strong_flow = 0
    if "Dòng Tiền" in df.columns:
        strong_flow = int(df["Dòng Tiền"].astype(str).str.contains("Mạnh|Tích cực", case=False, na=False).sum())

    return {
        "source": "scan",
        "total": total,
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "ad_ratio": ad_ratio,
        "above_ma20": above_ma20,
        "above_ma20_pct": round(above_ma20 / total * 100, 1) if total > 0 else 0,
        "strong_flow": strong_flow,
        "strong_flow_pct": round(strong_flow / total * 100, 1) if total > 0 else 0,
        "signal_counts": signal_counts,
    }


# ─────────────────────────────────────────────
# NGUỒN 2: TCBS Market Overview API (public)
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def breadth_from_tcbs() -> Optional[dict]:
    """
    Gọi TCBS API lấy advance/decline toàn sàn HOSE.
    Endpoint public, không cần auth.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://tcinvest.tcbs.com.vn/",
        }

        # TCBS market overview
        url = "https://apipubaws.tcbs.com.vn/stock-insight/v1/market/index-components?indexCode=VNINDEX"
        resp = requests.get(url, headers=headers, timeout=8)

        if resp.status_code != 200:
            return None

        data = resp.json()
        items = data.get("data", [])
        if not items:
            return None

        df = pd.DataFrame(items)
        total = len(df)

        # Cột thay đổi giá
        chg_col = None
        for c in ["priceChange", "changePercent", "change", "rs"]:
            if c in df.columns:
                chg_col = c
                break

        if chg_col:
            chg = pd.to_numeric(df[chg_col], errors="coerce").fillna(0)
            advancing = int((chg > 0).sum())
            declining  = int((chg < 0).sum())
            unchanged  = total - advancing - declining
        else:
            return None

        # MA20 — nếu có cột lastPrice & avgPrice20Day
        above_ma20 = 0
        above_ma20_pct = 0
        for price_col, ma_col in [("lastPrice", "avg20Day"), ("close", "ma20")]:
            if price_col in df.columns and ma_col in df.columns:
                p  = pd.to_numeric(df[price_col], errors="coerce")
                ma = pd.to_numeric(df[ma_col],    errors="coerce")
                above_ma20 = int((p > ma).sum())
                above_ma20_pct = round(above_ma20 / total * 100, 1)
                break

        # Đáy/Đỉnh 52 tuần
        new_high = new_low = 0
        if "week52High" in df.columns and "lastPrice" in df.columns:
            p  = pd.to_numeric(df["lastPrice"],  errors="coerce")
            h52 = pd.to_numeric(df["week52High"], errors="coerce")
            l52 = pd.to_numeric(df.get("week52Low", pd.Series([0]*len(df))), errors="coerce")
            new_high = int((p >= h52 * 0.99).sum())
            new_low  = int((p <= l52 * 1.01).sum())

        ad_ratio = round(advancing / declining, 2) if declining > 0 else float("inf")

        return {
            "source": "tcbs",
            "total": total,
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "ad_ratio": ad_ratio,
            "above_ma20": above_ma20,
            "above_ma20_pct": above_ma20_pct,
            "new_high_52w": new_high,
            "new_low_52w": new_low,
            "strong_flow": 0,
            "strong_flow_pct": 0,
            "signal_counts": {},
        }

    except Exception:
        return None


# ─────────────────────────────────────────────
# NGUỒN 3: SSI iBoard advance/decline (fallback)
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def breadth_from_ssi() -> Optional[dict]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://iboard.ssi.com.vn/",
            "Origin": "https://iboard.ssi.com.vn",
        }
        url = "https://iboard-query.ssi.com.vn/v2/stock/hose/snapshot"
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None

        data = resp.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(items, list) or not items:
            return None

        df = pd.DataFrame(items)
        total = len(df)

        chg_col = next((c for c in ["change", "priceChange", "pc"] if c in df.columns), None)
        if not chg_col:
            return None

        chg = pd.to_numeric(df[chg_col], errors="coerce").fillna(0)
        advancing = int((chg > 0).sum())
        declining  = int((chg < 0).sum())
        unchanged  = total - advancing - declining
        ad_ratio   = round(advancing / declining, 2) if declining > 0 else float("inf")

        # MA20
        above_ma20, above_ma20_pct = 0, 0
        for p_col, m_col in [("close", "ma20"), ("price", "avgPrice20")]:
            if p_col in df.columns and m_col in df.columns:
                p  = pd.to_numeric(df[p_col], errors="coerce")
                ma = pd.to_numeric(df[m_col], errors="coerce")
                above_ma20 = int((p > ma).sum())
                above_ma20_pct = round(above_ma20 / total * 100, 1)
                break

        return {
            "source": "ssi",
            "total": total,
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "ad_ratio": ad_ratio,
            "above_ma20": above_ma20,
            "above_ma20_pct": above_ma20_pct,
            "new_high_52w": 0,
            "new_low_52w": 0,
            "strong_flow": 0,
            "strong_flow_pct": 0,
            "signal_counts": {},
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
# HÀM CHÍNH: auto-pick nguồn tốt nhất
# ─────────────────────────────────────────────
def get_market_breadth(scan_results: list = None) -> Optional[dict]:
    """
    Ưu tiên: TCBS → SSI → scan_results
    Luôn bổ sung signal_counts từ scan nếu có.
    """
    result = breadth_from_tcbs()
    if result is None:
        result = breadth_from_ssi()

    # Bổ sung signal_counts từ scan dù dùng nguồn nào
    if scan_results:
        scan = breadth_from_scan(scan_results)
        if scan:
            if result is None:
                result = scan
            else:
                result["signal_counts"] = scan.get("signal_counts", {})
                result["strong_flow"]     = scan.get("strong_flow", 0)
                result["strong_flow_pct"] = scan.get("strong_flow_pct", 0)

    return result


# ─────────────────────────────────────────────
# RENDER UI — gọi từ main.py
# ─────────────────────────────────────────────
def render_breadth_panel(breadth: dict):
    """
    Hiển thị breadth thị trường: số lớn + progress bar.
    Dùng trong c3 bên dưới RSI/MACD.
    """
    if breadth is None:
        st.caption("⏳ Chưa có dữ liệu breadth — hãy chạy quét hoặc chờ API.")
        return

    total = breadth.get("total", 0)
    adv   = breadth.get("advancing", 0)
    dec   = breadth.get("declining", 0)
    unch  = breadth.get("unchanged", 0)
    adr   = breadth.get("ad_ratio", 0)

    source_label = {"tcbs": "TCBS", "ssi": "SSI iBoard", "scan": "Kết quả quét"}.get(
        breadth.get("source", ""), "—"
    )

    st.markdown(f"#### 📊 Breadth Thị Trường")
    st.caption(f"Nguồn: {source_label} · {total} mã")

    # --- Hàng 1: Tăng / Giảm / Đứng ---
    b1, b2, b3 = st.columns(3)
    b1.metric("🟢 Tăng", adv,  delta=f"{adv/total*100:.0f}%" if total else None)
    b2.metric("🔴 Giảm", dec,  delta=f"-{dec/total*100:.0f}%" if total else None, delta_color="inverse")
    b3.metric("⚪ Đứng", unch)

    # --- Progress bar tỷ lệ tăng/giảm ---
    adv_pct = adv / total if total > 0 else 0
    color_label = "🟢 Thị trường tích cực" if adv_pct > 0.55 else "🔴 Thị trường tiêu cực" if adv_pct < 0.40 else "🟡 Cân bằng"
    st.progress(adv_pct, text=f"{color_label} · A/D ratio: {adr}x")

    # --- Hàng 2: MA20 + new high/low ---
    ma20_pct = breadth.get("above_ma20_pct", 0)
    above_ma20 = breadth.get("above_ma20", 0)

    m1, m2 = st.columns(2)
    m1.metric("📈 Trên MA20", f"{above_ma20} mã", f"{ma20_pct:.0f}%")

    if breadth.get("new_high_52w") is not None and breadth.get("new_high_52w", 0) + breadth.get("new_low_52w", 0) > 0:
        m2.metric("🏔 Đỉnh 52T / Đáy 52T",
                  f"{breadth.get('new_high_52w', 0)} / {breadth.get('new_low_52w', 0)}")
    elif breadth.get("strong_flow", 0) > 0:
        m2.metric("💰 Dòng tiền mạnh", f"{breadth.get('strong_flow', 0)} mã",
                  f"{breadth.get('strong_flow_pct', 0):.0f}%")

    st.progress(
        min(ma20_pct / 100, 1.0),
        text=f"{'🟢' if ma20_pct > 50 else '🔴'} {ma20_pct:.0f}% mã trên MA20"
    )

    # --- Tín hiệu từ quét (nếu có) ---
    sig = breadth.get("signal_counts", {})
    if sig:
        st.markdown("**Phân bổ tín hiệu quét:**")
        sig_total = sum(sig.values())
        # Sắp xếp theo count giảm dần, hiển thị top 5
        for k, v in sorted(sig.items(), key=lambda x: -x[1])[:5]:
            pct = v / sig_total if sig_total > 0 else 0
            emoji = "🟢" if any(x in str(k) for x in ["Mua", "Tăng", "Tốt"]) else \
                    "🔴" if any(x in str(k) for x in ["Bán", "Giảm", "Xấu"]) else "🟡"
            st.progress(pct, text=f"{emoji} {k}: {v} mã ({pct*100:.0f}%)")
