"""
===============================================
💼 TAB PORTFOLIO v2 — SCREENER + QUẢN LÝ CHIẾN LƯỢC
===============================================
- PHẦN TRÊN:  SCREENER "ĐIỂM MUA VÀNG" (3 điều kiện)
- PHẦN DƯỚI:  4 MÃ × 25% danh mục
              Trạng thái: GIỮ CP | BÁN 25% | BÁN HẾT | CHỜ | MUA

Giao diện dùng chung bộ CSS tối (navy/purple) với tab "Sức Bật" để
đồng bộ trải nghiệm giữa các tab trong dashboard.
"""

import concurrent.futures
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

from data_loader import get_stock_data


# ══════════════════════════════════════════════
# 0. CSS DÙNG CHUNG (tham khảo tab Sức Bật)
# ══════════════════════════════════════════════

SB_CSS = """
<style>
.sb-header {
    background: linear-gradient(135deg,#1a1a2e,#16213e);
    border-radius: 12px; padding: 16px 20px; margin-bottom: 18px;
}
.sb-title { font-size: 22px; font-weight: 800; color: #e0e0ff; }
.sb-sub   { font-size: 12px; color: #888; margin-top: 2px; }
.sb-note {
    background: #1a1a2e; border-left: 3px solid #8b7fb5;
    padding: 10px 14px; border-radius: 0 8px 8px 0;
    font-size: 12px; color: #aaa; margin-bottom: 14px;
}
/* Card tra cứu */
.lk-card {
    background: #1e1e2e; border: 1px solid #2c2151;
    border-radius: 14px; padding: 20px 24px; margin-bottom: 16px;
}
.lk-ticker { font-size: 28px; font-weight: 800; color: #a78bfa; letter-spacing: 2px; }
.lk-company { font-size: 13px; color: #888; margin-top: 2px; margin-bottom: 16px; }
.lk-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 14px; }
.lk-metric { background: #12102a; border-radius: 10px; padding: 12px 14px; }
.lk-label { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: .5px; }
.lk-value { font-size: 22px; font-weight: 700; color: #e0e0ff; margin-top: 3px; }
.lk-sub   { font-size: 10px; color: #555; margin-top: 2px; }
.val-up   { color: #00e676 !important; }
.val-down { color: #ff5252 !important; }
.val-warn { color: #ffd740 !important; }
.lk-section { font-size: 11px; color: #8b7fb5; text-transform: uppercase;
               letter-spacing: .6px; margin: 14px 0 8px;
               border-bottom: 1px solid #2c2151; padding-bottom: 4px; }
.sr-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.sr-table th { color: #666; font-weight: 400; text-align: left;
               padding: 4px 8px; font-size: 11px; text-transform: uppercase; }
.sr-table td { padding: 5px 8px; border-bottom: 1px solid #1e1a33; color: #ccc; }
.sr-table tr:last-child td { border-bottom: none; }
.badge-r { background:#3a1a1a; color:#ff5252; padding:2px 8px;
           border-radius:4px; font-size:11px; font-weight:600; }
.badge-s { background:#1a3a1a; color:#00e676; padding:2px 8px;
           border-radius:4px; font-size:11px; font-weight:600; }
.badge-fib { background:#1a1a3a; color:#7c9ef5; padding:2px 6px;
             border-radius:4px; font-size:10px; }
.formula-note {
    background: #12102a; border-left: 3px solid #a78bfa;
    padding: 10px 14px; border-radius: 0 8px 8px 0;
    font-size: 12px; color: #999; margin-top: 12px; line-height: 1.7;
}
/* scan section */
.sb-stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.sb-stat { background: #1e1e2e; border-radius: 10px; padding: 10px 16px;
           flex: 1; min-width: 130px; }
.sb-stat-label { font-size: 11px; color: #888; text-transform: uppercase; }
.sb-stat-value { font-size: 20px; font-weight: 800; color: #e0e0ff; margin-top: 2px; }
.src-badge { display:inline-block; padding:1px 7px; border-radius:10px;
             font-size:10px; font-weight:600; margin-left:6px; }
.src-vci     { background:#1a2a3a; color:#5b9bd5; }
.src-fireant { background:#1a2e1a; color:#4caf50; }
.src-yahoo   { background:#1a1a3a; color:#8b7fb5; }

/* ── Mở rộng riêng cho tab Portfolio v2 ── */
.badge-hold    { background:#3a2f14; color:#ffd740; padding:2px 8px;
                 border-radius:4px; font-size:11px; font-weight:600; }
.badge-sell25  { background:#3a2414; color:#ffab40; padding:2px 8px;
                 border-radius:4px; font-size:11px; font-weight:600; }
.badge-sellall { background:#3a1a1a; color:#ff5252; padding:2px 8px;
                 border-radius:4px; font-size:11px; font-weight:600; }
.badge-buy     { background:#1a3a1a; color:#00e676; padding:2px 8px;
                 border-radius:4px; font-size:11px; font-weight:600; }
.badge-wait    { background:#1e1a33; color:#8b7fb5; padding:2px 8px;
                 border-radius:4px; font-size:11px; font-weight:600; }

.slot-card {
    background: #1e1e2e; border: 1px solid #2c2151;
    border-radius: 14px; padding: 18px 10px 14px 10px;
    text-align: center; min-height: 108px;
}
.slot-card.empty {
    background: #16162a; border: 2px dashed #3a2f66;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.slot-empty-plus { color: #5a4a8a; font-size: 1.8rem; line-height: 1; }
.slot-empty-label { color: #5a4a8a; font-size: .75rem; margin-top: 4px; }
.slot-ticker { font-weight: 800; font-size: 1.15rem; color: #e0e0ff; letter-spacing: .5px; }
.slot-pct { font-size: .72rem; color: #888; margin-top: 2px; }
.slot-action-wrap { margin-top: 10px; }

.buy-confirm-card {
    background: #12102a; border: 1px solid #1a3a1a;
    border-radius: 10px; padding: 12px 10px; text-align: center;
}
.buy-confirm-ticker { font-weight: 700; font-size: 1rem; color: #e0e0ff; }
.buy-confirm-note { font-size: .75rem; color: #00e676; margin-top: 4px; }
</style>
"""


def _inject_css():
    if not st.session_state.get("_sb_css_injected"):
        st.markdown(SB_CSS, unsafe_allow_html=True)
        st.session_state["_sb_css_injected"] = True


# ══════════════════════════════════════════════
# 1. SESSION STATE
# ══════════════════════════════════════════════

# 4 slot cố định, mỗi slot 25%
SLOT_COUNT = 4
SLOT_PCT   = 25  # % mỗi mã

ACTIONS = ["GIỮ CP", "BÁN 25%", "BÁN HẾT", "MUA", "CHỜ"]

# Badge class + màu dùng cho từng trạng thái (đồng bộ với SB_CSS ở trên)
ACTION_BADGE = {
    "GIỮ CP":  {"class": "badge-hold",    "color": "#ffd740"},
    "BÁN 25%": {"class": "badge-sell25",  "color": "#ffab40"},
    "BÁN HẾT": {"class": "badge-sellall", "color": "#ff5252"},
    "MUA":     {"class": "badge-buy",     "color": "#00e676"},
    "CHỜ":     {"class": "badge-wait",    "color": "#8b7fb5"},
}

MARKET_BADGE = {
    "Uptrend":   {"class": "badge-buy",     "label": "🟢 Uptrend"},
    "Sideways":  {"class": "badge-hold",    "label": "🟡 Sideways"},
    "Downtrend": {"class": "badge-sellall", "label": "🔴 Downtrend"},
}


def _init_state():
    # Mỗi slot lưu trực tiếp qua 2 key widget pv2_ticker_i / pv2_action_i
    # (nguồn dữ liệu duy nhất — tránh lệch giữa card hiển thị và ô nhập liệu)
    for i in range(SLOT_COUNT):
        st.session_state.setdefault(f"pv2_ticker_{i}", "")
        st.session_state.setdefault(f"pv2_action_{i}", "CHỜ")
    if 'pv2_scan_results' not in st.session_state:
        st.session_state.pv2_scan_results = []
    if 'pv2_last_updated' not in st.session_state:
        st.session_state.pv2_last_updated = ""
    if 'pv2_market_state' not in st.session_state:
        st.session_state.pv2_market_state = "Sideways"


def _get_slots():
    """Đọc trạng thái 4 slot hiện tại từ session_state (nguồn duy nhất)."""
    return [
        {"ticker": st.session_state[f"pv2_ticker_{i}"], "action": st.session_state[f"pv2_action_{i}"]}
        for i in range(SLOT_COUNT)
    ]


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
        <div class="slot-card empty">
            <div class="slot-empty-plus">+</div>
            <div class="slot-empty-label">Slot {slot_idx+1} · {pct}%</div>
        </div>
        """
    badge = ACTION_BADGE.get(action, ACTION_BADGE["CHỜ"])
    return f"""
    <div class="slot-card">
        <div class="slot-ticker">{ticker}</div>
        <div class="slot-pct">{pct}% danh mục</div>
        <div class="slot-action-wrap">
            <span class="{badge['class']}">{action}</span>
        </div>
    </div>
    """


# ══════════════════════════════════════════════
# 4. MAIN RENDER — gộp Screener + Danh mục vào 1 khối gọn
# ══════════════════════════════════════════════

def render_portfolio_v2_tab(priority_tickers=None):
    _inject_css()
    _init_state()

    market_state = st.session_state.pv2_market_state
    mkt = MARKET_BADGE.get(market_state, MARKET_BADGE["Sideways"])
    now_str = st.session_state.pv2_last_updated or datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # ── Header dashboard (đúng theo mẫu) + chọn trạng thái thị trường ──
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown(f"""
        <div class="sb-header">
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                <span class="sb-title">📊 Dashboard — Chiến lược 4 mã × 25%</span>
                <span class="sb-sub" style="margin:0;">● Cập nhật {now_str}</span>
                <span class="{mkt['class']}">{mkt['label']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with h2:
        new_market_state = st.selectbox(
            "Thị trường", ["Uptrend", "Sideways", "Downtrend"],
            index=["Uptrend", "Sideways", "Downtrend"].index(market_state),
            key="pv2_mkt_state", label_visibility="collapsed",
        )
        if new_market_state != market_state:
            st.session_state.pv2_market_state = new_market_state
            st.rerun()

    # ── 4 slot: card hiển thị + nhập mã / chiến lược ngay bên dưới ──
    cols = st.columns(4)
    for i in range(4):
        ticker = st.session_state[f"pv2_ticker_{i}"]
        action = st.session_state[f"pv2_action_{i}"]
        with cols[i]:
            st.markdown(_slot_card_html(i, ticker, action), unsafe_allow_html=True)
            st.text_input("Mã", key=f"pv2_ticker_{i}", placeholder=f"Mã slot {i+1}",
                          label_visibility="collapsed")
            st.selectbox("Chiến lược", ACTIONS,
                         index=ACTIONS.index(st.session_state[f"pv2_action_{i}"]),
                         key=f"pv2_action_{i}", label_visibility="collapsed")
    # chuẩn hoá mã vừa gõ thành chữ hoa
    for i in range(4):
        t = st.session_state[f"pv2_ticker_{i}"].strip().upper()
        if t != st.session_state[f"pv2_ticker_{i}"]:
            st.session_state[f"pv2_ticker_{i}"] = t

    slots = _get_slots()

    # ── Đặt hàng loạt (chỉ 1 dòng nút gọn) ──
    bulk_cols = st.columns(5)
    labels = ["🟡 GIỮ tất cả", "🟠 BÁN 25%", "🔴 BÁN HẾT", "🟢 MUA tất cả", "⚪ CHỜ tất cả"]
    for i, (action, label) in enumerate(zip(ACTIONS, labels)):
        with bulk_cols[i]:
            if st.button(label, key=f"pv2_bulk_{i}", use_container_width=True):
                for j in range(4):
                    if st.session_state[f"pv2_ticker_{j}"]:
                        st.session_state[f"pv2_action_{j}"] = action
                st.session_state.pv2_last_updated = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                st.rerun()

    # ── Sổ lệnh mua hôm nay (chỉ hiện khi có mã đang MUA) ──
    buy_slots = [s for s in slots if s["ticker"] and s["action"] == "MUA"]
    if buy_slots:
        bcols = st.columns(len(buy_slots))
        for col, s in zip(bcols, buy_slots):
            with col:
                st.markdown(f"""
                <div class="buy-confirm-card">
                    <div class="buy-confirm-ticker">{s['ticker']}</div>
                    <div class="buy-confirm-note">✓ đã vào sổ lệnh</div>
                </div>
                """, unsafe_allow_html=True)

    # ── Screener gộp gọn trong 1 expander — tìm mã rồi nạp thẳng vào 4 slot ──
    with st.expander("🎯 Tìm mã đề xuất (Screener điểm mua vàng)", expanded=False):
        st.caption("3 điều kiện: Giá vùng rẻ 129d · RSI 2 đáy nâng · Volume kiệt cung")

        c1, c2, c3, c4 = st.columns(4)
        max_position = c1.slider("📉 Vùng giá rẻ 129d ≤", 0.10, 0.60, 0.35, 0.05)
        max_rsi      = c2.slider("🔻 RSI coi là đáy ≤", 25.0, 45.0, 35.0, 1.0)
        min_rsi_gap  = c3.slider("📐 Khoảng cách RSI 2 đáy", 1.0, 10.0, 2.0, 0.5)
        dry_ratio    = c4.slider("🥵 Volume cạn ≤ (× MA20)", 0.20, 0.80, 0.45, 0.05)

        custom = st.text_input(
            "🏷️ Danh sách mã quét (để trống = dùng danh sách VN30 ưu tiên)",
            placeholder="VD: PVT, FPT, HPG, VCB ...", key="pv2_custom_input",
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

        results = st.session_state.pv2_scan_results
        if results:
            df_res = pd.DataFrame(results)

            st.markdown(f"""
            <div class="sb-stat-row">
                <div class="sb-stat">
                    <div class="sb-stat-label">Mã đạt điểm mua vàng</div>
                    <div class="sb-stat-value">{len(results)}</div>
                </div>
                <div class="sb-stat">
                    <div class="sb-stat-label">Score cao nhất</div>
                    <div class="sb-stat-value">{results[0]['Score']}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(df_res, use_container_width=True, hide_index=True,
                column_config={
                    'Vị thế 129d': st.column_config.ProgressColumn(
                        "Vị thế 129d", min_value=0.0, max_value=1.0, format="%.0f%%"),
                    'Vol/MA20': st.column_config.NumberColumn("Vol/MA20", format="%.2f x"),
                })

            if st.button("📥 Nạp top 4 mã đẹp nhất vào danh mục", type="primary"):
                top4 = results[:4]
                for i, r in enumerate(top4):
                    st.session_state[f"pv2_ticker_{i}"] = r['Mã CP']
                    st.session_state[f"pv2_action_{i}"] = "MUA"
                st.session_state.pv2_last_updated = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                st.rerun()
        else:
            st.markdown(
                '<div class="sb-note">Nhấn <b>🎯 QUÉT ĐIỂM MUA</b> để tìm cơ hội thật — '
                'kết quả sẽ hiện tại đây, có thể nạp thẳng vào 4 slot bên trên.</div>',
                unsafe_allow_html=True,
            )

    # Quy tắc Mua/Bán/Chờ không hiển thị công khai nữa — chỉ hệ thống
    # dùng nội bộ để tính khuyến nghị (xem gợi ý theo market_state ở trên).

if __name__ == "__main__":
    st.set_page_config(page_title="Portfolio v2", layout="wide")
    render_portfolio_v2_tab()
