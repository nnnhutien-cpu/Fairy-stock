"""
===============================================
💼 TAB PORTFOLIO v2 — SCREENER + QUẢN LÝ CHIẾN LƯỢC
===============================================
- PHẦN TRÊN:  SCREENER "ĐIỂM MUA VÀNG" (3 điều kiện)
- PHẦN DƯỚI:  4 MÃ × 25% danh mục
              Trạng thái: GIỮ CP | BÁN 25% | BÁN HẾT | CHỜ | MUA
"""

import concurrent.futures
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

from data_loader import get_stock_data


# ══════════════════════════════════════════════
# 1. SESSION STATE
# ══════════════════════════════════════════════

# 4 slot cố định, mỗi slot 25%
SLOT_COUNT = 4
SLOT_PCT   = 25  # % mỗi mã

ACTIONS = ["GIỮ CP", "BÁN 25%", "BÁN HẾT", "MUA", "CHỜ"]

ACTION_STYLE = {
    "GIỮ CP":  {"bg": "#fdf6e3", "border": "#c8a84b", "color": "#7a5c00"},
    "BÁN 25%": {"bg": "#fff3e0", "border": "#e08030", "color": "#8a3a00"},
    "BÁN HẾT": {"bg": "#fce8e8", "border": "#d94040", "color": "#8a0000"},
    "MUA":     {"bg": "#e8f5e8", "border": "#3aaa3a", "color": "#1a5c1a"},
    "CHỜ":     {"bg": "#f2f2f2", "border": "#aaaaaa", "color": "#555555"},
}


def _init_state():
    if 'pv2_slots' not in st.session_state:
        # 4 slot: mỗi slot là dict {ticker, action}
        st.session_state.pv2_slots = [
            {"ticker": "", "action": "CHỜ"} for _ in range(SLOT_COUNT)
        ]
    if 'pv2_scan_results' not in st.session_state:
        st.session_state.pv2_scan_results = []
    if 'pv2_last_updated' not in st.session_state:
        st.session_state.pv2_last_updated = ""
    if 'pv2_market_state' not in st.session_state:
        st.session_state.pv2_market_state = "Sideways"


# ══════════════════════════════════════════════
# 2. SCREENER LOGIC
# ══════════════════════════════════════════════

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/period, min_periods=period).mean()
    al = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    m = {}
    for col in df.columns:
        lc = str(col).lower().strip()
        if lc in ('close','price','c','gia','giá'):
            m[col] = 'close'
        elif lc in ('volume','vol','v','khối lượng','matchvolume'):
            m[col] = 'volume'
    df = df.rename(columns=m)
    for c in ('close','volume'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.dropna(subset=['close'])


def _check_val129(df, max_pos=0.35):
    close = df['close'].iloc[-129:]
    if len(close) < 60:
        return None
    lo, hi = close.min(), close.max()
    if hi <= lo:
        return None
    pos = (close.iloc[-1] - lo) / (hi - lo)
    return {'ok': pos <= max_pos, 'position': round(pos, 2)}


def _find_rsi_bottoms(rsi, close, max_rsi, win=2):
    vals = rsi.values
    bottoms = []
    for i in range(win, len(vals)-win):
        seg = vals[i-win:i+win+1]
        if vals[i] <= seg.min() and vals[i] <= max_rsi:
            if bottoms and (i - bottoms[-1]['idx']) < 4:
                if vals[i] < bottoms[-1]['rsi']:
                    bottoms[-1] = {'idx':i,'rsi':vals[i],'price':close.iloc[i],'date':rsi.index[i]}
                continue
            bottoms.append({'idx':i,'rsi':vals[i],'price':close.iloc[i],'date':rsi.index[i]})
    return bottoms


def _check_rsi2bot(df, max_rsi=35.0, min_gap=2.0, min_days=5, b2_max_age=25):
    close = df['close']
    rsi   = _rsi(close)
    if len(rsi) < 134:
        return None
    rsi_w  = rsi.iloc[-120:]
    close_w = close.iloc[-120:]
    bottoms = _find_rsi_bottoms(rsi_w, close_w, max_rsi)
    if len(bottoms) < 2:
        return None
    n = len(rsi_w)
    for j in range(len(bottoms)-1, 0, -1):
        b2 = bottoms[j]
        if (n-1) - b2['idx'] > b2_max_age:
            continue
        for k in range(j-1, -1, -1):
            b1 = bottoms[k]
            if (b2['idx']-b1['idx']) < min_days:
                continue
            gap = b2['rsi'] - b1['rsi']
            if gap < min_gap:
                continue
            if b2['price'] > b1['price'] * 1.05:
                continue
            return {
                'ok': True,
                'b1_rsi': round(b1['rsi'],1), 'b2_rsi': round(b2['rsi'],1),
                'gap': round(gap,1),
                'b1_date': pd.Timestamp(b1['date']).strftime('%d/%m'),
                'b2_date': pd.Timestamp(b2['date']).strftime('%d/%m'),
                'rsi_now': round(rsi.iloc[-1],1),
            }
    return None


def _check_vol_dryup(df, dry_ratio=0.45):
    vol = df['volume']
    if vol.sum() <= 0 or len(vol) < 30:
        return None
    ma20 = vol.rolling(20).mean().iloc[-1]
    if not ma20 or ma20 <= 0:
        return None
    ratio = min(vol.iloc[-1]/ma20, vol.iloc[-3:].mean()/ma20)
    return {'ok': ratio <= dry_ratio, 'ratio': round(ratio,2)}


@st.cache_data(ttl=900, show_spinner=False)
def _analyze_ticker(ticker, days, max_rsi, min_gap, dry_ratio, max_pos):
    try:
        df = get_stock_data(ticker, days_back=days)
        if df is None or df.empty:
            return None
        df = _normalize(df)
        if len(df) < 150 or 'volume' not in df.columns:
            return None
        val  = _check_val129(df, max_pos=max_pos)
        rsi2 = _check_rsi2bot(df, max_rsi=max_rsi, min_gap=min_gap)
        vol  = _check_vol_dryup(df, dry_ratio=dry_ratio)
        if not (val and val['ok'] and rsi2 and rsi2['ok'] and vol and vol['ok']):
            return None
        score = round(
            max(0.0, max_pos - val['position']) * 60
            + max(0.0, rsi2['gap']) * 1.5
            + max(0.0, dry_ratio - vol['ratio']) * 80
        , 1)
        return {
            'Mã CP': ticker,
            'Giá': round(df['close'].iloc[-1], 2),
            'RSI đáy 1': rsi2['b1_rsi'],
            'RSI đáy 2': rsi2['b2_rsi'],
            'ΔRSI': rsi2['gap'],
            'Ngày đáy 1': rsi2['b1_date'],
            'Ngày đáy 2': rsi2['b2_date'],
            'RSI hiện tại': rsi2['rsi_now'],
            'Vol/MA20': vol['ratio'],
            'Vị thế 129d': val['position'],
            'Score': score,
        }
    except Exception:
        return None


# ══════════════════════════════════════════════
# 3. CARD RENDERER
# ══════════════════════════════════════════════

def _slot_card_html(slot_idx, ticker, action, pct=25):
    """Render 1 slot card — trống thì hiện dấu +"""
    if not ticker:
        return f"""
        <div style="
            background:#1e1640; border:2px dashed #4a3a7a;
            border-radius:12px; padding:18px 10px;
            text-align:center; min-height:100px;
            display:flex; flex-direction:column;
            align-items:center; justify-content:center;
        ">
            <div style="color:#5a4a8a; font-size:1.8rem; line-height:1;">+</div>
            <div style="color:#5a4a8a; font-size:.75rem; margin-top:4px;">Slot {slot_idx+1} · {pct}%</div>
        </div>
        """
    st_cfg = ACTION_STYLE.get(action, ACTION_STYLE["CHỜ"])
    return f"""
    <div style="
        background:{st_cfg['bg']};
        border:2px solid {st_cfg['border']};
        border-radius:12px; padding:16px 10px 12px 10px;
        text-align:center; min-height:100px;
    ">
        <div style="
            font-weight:800; font-size:1.1rem;
            color:#111111; letter-spacing:.5px;
        ">{ticker}</div>
        <div style="
            font-size:.72rem; color:#666; margin-top:2px;
        ">{pct}% danh mục</div>
        <div style="
            font-size:.82rem; font-weight:700;
            color:{st_cfg['color']};
            margin-top:8px;
            background:rgba(0,0,0,.06);
            border-radius:6px; padding:3px 0;
        ">{action}</div>
    </div>
    """


def _render_dashboard(slots, now_str, market_state):
    """Header + 4 card slots"""
    state_color = {"Uptrend": "#40c040", "Sideways": "#c0a020", "Downtrend": "#d04040"}.get(market_state, "#888")

    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap;">
        <span style="font-size:1.25rem; font-weight:700;">📊 Dashboard — Chiến lược 4 mã × 25%</span>
        <span style="color:#40c040; font-size:.82rem;">● Cập nhật {now_str}</span>
        <span style="
            border:1px solid {state_color}; color:{state_color};
            border-radius:20px; padding:2px 12px; font-size:.82rem;
        ">{market_state}</span>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(4)
    for i, slot in enumerate(slots):
        with cols[i]:
            st.markdown(
                _slot_card_html(i, slot["ticker"], slot["action"]),
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════
# 4. MAIN RENDER
# ══════════════════════════════════════════════

def render_portfolio_v2_tab(priority_tickers=None):
    _init_state()

    # ─── PHẦN 1: SCREENER ──────────────────────────────────────────
    st.markdown("### 🎯 PHẦN 1 — SCREENER ĐIỂM MUA VÀNG")
    st.caption("3 điều kiện: Giá vùng rẻ 129d · RSI 2 đáy nâng · Volume kiệt cung")

    with st.expander("⚙️ Cấu hình ngưỡng lọc", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        max_position = c1.slider("📉 Vùng giá rẻ 129d ≤", 0.10, 0.60, 0.35, 0.05)
        max_rsi      = c2.slider("🔻 RSI coi là đáy ≤", 25.0, 45.0, 35.0, 1.0)
        min_rsi_gap  = c3.slider("📐 Khoảng cách RSI 2 đáy", 1.0, 10.0, 2.0, 0.5)
        dry_ratio    = c4.slider("🥵 Volume cạn ≤ (× MA20)", 0.20, 0.80, 0.45, 0.05)

    custom = st.text_input(
        "🏷️ Danh sách mã quét (để trống = dùng danh sách VN30 ưu tiên)",
        placeholder="VD: PVT, FPT, HPG, VCB ...",
        key="pv2_custom_input",
    )
    tickers = [t.strip().upper() for t in custom.replace(',', ' ').split()] if custom.strip() \
              else list(priority_tickers or [])

    if st.button("🎯 QUÉT ĐIỂM MUA", type="primary"):
        if not tickers:
            st.warning("Chưa có danh sách mã.")
            st.stop()
        results = []
        with st.status(f"Đang soi {len(tickers)} mã...", expanded=True) as status:
            bar = st.progress(0)
            done = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(_analyze_ticker, t, 300,
                                   max_rsi, min_rsi_gap, dry_ratio, max_position): t
                        for t in tickers}
                for f in concurrent.futures.as_completed(futs):
                    done += 1
                    bar.progress(done / len(tickers))
                    status.update(label=f"Soi {done}/{len(tickers)} mã...")
                    try:
                        r = f.result()
                        if r:
                            results.append(r)
                    except Exception:
                        pass
            status.update(
                label=f"✅ Hoàn tất — {len(results)} mã đạt ĐIỂM MUA VÀNG",
                state="complete", expanded=bool(results),
            )
        st.session_state.pv2_scan_results = sorted(results, key=lambda x: x['Score'], reverse=True)
        st.session_state.pv2_last_updated = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # ── Kết quả quét ──
    results = st.session_state.pv2_scan_results
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"🏆 **{len(results)}** mã đạt cả 3 điều kiện")

        with st.expander("📋 Bảng chi tiết", expanded=True):
            st.dataframe(df_res, use_container_width=True, hide_index=True,
                column_config={
                    'Vị thế 129d': st.column_config.ProgressColumn(
                        "Vị thế 129d", min_value=0.0, max_value=1.0, format="%.0f%%"),
                    'Vol/MA20': st.column_config.NumberColumn("Vol/MA20", format="%.2f x"),
                })

        # Nạp top 4 vào 4 slot
        st.markdown("#### 💡 Nạp vào 4 slot (25% mỗi mã)")
        if st.button("📥 Nạp top 4 mã đẹp nhất vào danh mục", type="primary"):
            top4 = results[:4]
            for i, r in enumerate(top4):
                st.session_state.pv2_slots[i] = {"ticker": r['Mã CP'], "action": "MUA"}
            # Slot thừa nếu ít hơn 4 mã → giữ nguyên
            st.session_state.pv2_last_updated = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            st.success("✅ Đã nạp! Xem bảng chiến lược bên dưới.")
            st.rerun()

    else:
        with st.expander("📖 Chiến lược hoạt động như thế nào? (ví dụ minh họa)", expanded=False):
            st.markdown("""
            > ⚠️ **Đây là ví dụ MINH HỌA** — không phải kết quả quét thật.

            | Điều kiện | Ví dụ PVT | Đạt? |
            |---|---|---|
            | RSI 2 đáy nâng | Đáy 1 = 21 → Đáy 2 = 28 (giá không giảm thêm) | ✅ |
            | Volume kiệt cung | 1tr CP vs TB20 = 3tr → 0.33× | ✅ |
            | Định giá rẻ 129d | Giá ở vùng < 35% biên độ 129 phiên | ✅ |
            """)
        st.info("Nhấn **🎯 QUÉT ĐIỂM MUA** để tìm cơ hội thật.")

    st.divider()

    # ─── PHẦN 2: 4 SLOT × 25% ──────────────────────────────────────
    st.markdown("### 💼 PHẦN 2 — DANH MỤC 4 MÃ × 25%")

    # Header controls
    hc1, hc2 = st.columns([2, 3])
    with hc1:
        market_state = st.selectbox(
            "📊 Trạng thái thị trường",
            ["Uptrend", "Sideways", "Downtrend"],
            index=["Uptrend","Sideways","Downtrend"].index(
                st.session_state.pv2_market_state
                if st.session_state.pv2_market_state in ["Uptrend","Sideways","Downtrend"]
                else "Sideways"
            ),
            key="pv2_mkt_state",
        )
        if market_state != st.session_state.pv2_market_state:
            st.session_state.pv2_market_state = market_state

    # Gợi ý hành động tự động dựa thị trường
    with hc2:
        if market_state == "Downtrend":
            st.error("⚠️ Thị trường **Downtrend** — khuyến nghị **BÁN HẾT** toàn bộ, chuyển CHỜ")
        elif market_state == "Sideways":
            st.warning("🟡 Thị trường **Sideways** — cân nhắc **BÁN 25%** mã yếu, giữ mã mạnh")
        else:
            st.success("🟢 Thị trường **Uptrend** — duy trì **GIỮ CP**, chỉ bán khi đạt mục tiêu")

    now_str = st.session_state.pv2_last_updated or datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # ── 4 CARD SLOTS ──
    _render_dashboard(st.session_state.pv2_slots, now_str, market_state)

    # ── Kết quả đặt lệnh hôm nay (mã đang MUA) ──
    buy_slots = [(i, s) for i, s in enumerate(st.session_state.pv2_slots)
                 if s["ticker"] and s["action"] == "MUA"]
    if buy_slots:
        st.markdown("---")
        st.markdown("**Kết quả đặt lệnh hôm nay** — xác nhận trên sổ lệnh")
        bcols = st.columns(len(buy_slots))
        for col, (i, s) in zip(bcols, buy_slots):
            with col:
                st.markdown(f"""
                <div style="
                    background:#e8f5e8; border:2px solid #40c040;
                    border-radius:10px; padding:12px 10px; text-align:center;
                ">
                    <div style="font-weight:700; font-size:1rem;">{s['ticker']}</div>
                    <div style="font-size:.75rem; color:#20a020; margin-top:4px;">✓ đã vào sổ lệnh</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── EDITOR 4 SLOT ──
    st.markdown("#### 🎛️ Chỉnh sửa từng slot")

    slot_cols = st.columns(4)
    for i in range(4):
        with slot_cols[i]:
            st.markdown(f"**Slot {i+1} · 25%**")
            slot = st.session_state.pv2_slots[i]

            new_ticker = st.text_input(
                "Mã CP", value=slot["ticker"],
                placeholder="VD: FPT",
                key=f"pv2_ticker_{i}",
            ).upper().strip()

            new_action = st.selectbox(
                "Chiến lược",
                ACTIONS,
                index=ACTIONS.index(slot["action"]) if slot["action"] in ACTIONS else 4,
                key=f"pv2_action_{i}",
            )

            if st.button("💾 Lưu", key=f"pv2_save_{i}", use_container_width=True):
                st.session_state.pv2_slots[i] = {"ticker": new_ticker, "action": new_action}
                st.session_state.pv2_last_updated = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                st.rerun()

    st.divider()

    # ── Đặt hàng loạt ──
    st.markdown("#### ⚡ Đặt chiến lược hàng loạt")
    bulk_cols = st.columns(5)
    labels = ["🟡 GIỮ tất cả", "🟠 BÁN 25% tất cả", "🔴 BÁN HẾT tất cả", "🟢 MUA tất cả", "⚪ CHỜ tất cả"]
    for i, (action, label) in enumerate(zip(ACTIONS, labels)):
        with bulk_cols[i]:
            if st.button(label, key=f"pv2_bulk_{i}", use_container_width=True):
                for s in st.session_state.pv2_slots:
                    if s["ticker"]:  # chỉ slot có mã
                        s["action"] = action
                st.session_state.pv2_last_updated = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                st.rerun()

    # ── Quy tắc ──
    with st.expander("📖 Quy tắc Mua / Bán / Chờ", expanded=False):
        st.markdown("""
        | Thị trường | Hành động khuyến nghị |
        |---|---|
        | **Uptrend** | GIỮ CP — chỉ bán khi đạt mục tiêu lãi |
        | **Sideways** | BÁN 25% mã yếu nhất, dùng room mua mã mạnh hơn |
        | **Downtrend** | BÁN HẾT toàn bộ → CHỜ 100% tiền mặt |

        **🟢 MUA KHI:** Mã xuất hiện trong screener ĐIỂM MUA VÀNG (3 điều kiện đồng thời)

        **⚪ CHỜ KHI:** Sau khi cắt lỗ — không bắt đáy ngay. Đợi tín hiệu mới từ screener.

        **Cơ cấu:** 4 mã × 25% — cân bằng, không tập trung quá vào 1 mã.
        """)


if __name__ == "__main__":
    st.set_page_config(page_title="Portfolio v2", layout="wide")
    render_portfolio_v2_tab()
