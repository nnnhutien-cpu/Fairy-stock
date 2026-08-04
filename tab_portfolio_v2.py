"""
===============================================
💼 TAB PORTFOLIO v2 — SCREENER + QUẢN LÝ GIAO DỊCH
===============================================
Gộp 2 chức năng trong 1 tab:

  🔝 PHẦN TRÊN:  SCREENER "ĐIỂM MUA VÀNG"
                  - Định giá rẻ (vùng dưới của biên độ 129 ngày)
                  - RSI tạo 2 đáy nâng (phân kỳ dương)
                  - Volume kiệt cung dưới MA20
                  → Chọn 4 mã đẹp nhất

  🔻 PHẦN DƯỚI:  QUẢN LÝ GIAO DỊCH 4 MÃ (10-20-30-40)
                  - Theo dõi giá, lãi/lỗ real-time
                  - Nút nhanh: MUA / GIỮ / CẮT LỖ / CHỜ
                  - Quy tắc tự động: bán hết khi xấu, luân chuyển vốn

TÍCH HỢP VÀO main.py:
    from tab_portfolio_v2 import render_portfolio_v2_tab
    with tab_portfolio_v2:
        render_portfolio_v2_tab(PRIORITY_TICKERS)
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

def _init_state():
    if 'pv2_portfolio' not in st.session_state:
        st.session_state.pv2_portfolio = {
            'stocks':         ['VN30-1', 'VN30-2', 'VN30-3', 'VN30-4'],
            'allocations':    [10, 20, 30, 40],
            'status':         ['CHỜ', 'CHỜ', 'CHỜ', 'CHỜ'],
            'buy_prices':     [0.0, 0.0, 0.0, 0.0],
            'current_prices': [0.0, 0.0, 0.0, 0.0],
            'quantities':     [0, 0, 0, 0],
            'notes':          ['', '', '', ''],
            'last_updated':   datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    if 'pv2_total_capital' not in st.session_state:
        st.session_state.pv2_total_capital = 100_000_000
    if 'pv2_scan_results' not in st.session_state:
        st.session_state.pv2_scan_results = []


# ══════════════════════════════════════════════
# 2. SCREENER: 3 ĐIỀU KIỆN "ĐIỂM MUA VÀNG"
# ══════════════════════════════════════════════

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    m = {}
    for col in df.columns:
        lc = str(col).lower().strip()
        if lc in ('close', 'price', 'c', 'gia', 'giá'):
            m[col] = 'close'
        elif lc in ('volume', 'vol', 'v', 'khối lượng', 'matchvolume'):
            m[col] = 'volume'
    df = df.rename(columns=m)
    for c in ('close', 'volume'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.dropna(subset=['close'])


def check_valuation_129(df, lookback=129, max_pos=0.35):
    """Giá nằm trong vùng rẻ nhất của 129 phiên"""
    close = df['close'].iloc[-lookback:]
    if len(close) < 60:
        return None
    lo, hi = close.min(), close.max()
    if hi <= lo:
        return None
    pos = (close.iloc[-1] - lo) / (hi - lo)
    return {'ok': pos <= max_pos, 'position': round(pos, 2),
            'low129': round(lo, 2), 'high129': round(hi, 2)}


def _find_rsi_bottoms(rsi, close, max_rsi, win=2):
    vals = rsi.values
    bottoms = []
    for i in range(win, len(vals) - win):
        seg = vals[i - win:i + win + 1]
        if vals[i] <= seg.min() and vals[i] <= max_rsi:
            if bottoms and (i - bottoms[-1]['idx']) < 4:
                if vals[i] < bottoms[-1]['rsi']:
                    bottoms[-1] = {'idx': i, 'rsi': vals[i],
                                   'price': close.iloc[i], 'date': rsi.index[i]}
                continue
            bottoms.append({'idx': i, 'rsi': vals[i],
                            'price': close.iloc[i], 'date': rsi.index[i]})
    return bottoms


def check_rsi_double_bottom(df, lookback=120, max_rsi=35.0,
                             min_gap=2.0, min_days=5, b2_max_age=25):
    """RSI 2 đáy nâng — phân kỳ dương"""
    close = df['close']
    rsi = _rsi(close)
    if len(rsi) < lookback + 14:
        return None
    rsi_w = rsi.iloc[-lookback:]
    close_w = close.iloc[-lookback:]
    bottoms = _find_rsi_bottoms(rsi_w, close_w, max_rsi)
    if len(bottoms) < 2:
        return None
    n = len(rsi_w)
    for j in range(len(bottoms) - 1, 0, -1):
        b2 = bottoms[j]
        if (n - 1) - b2['idx'] > b2_max_age:
            continue
        for k in range(j - 1, -1, -1):
            b1 = bottoms[k]
            if (b2['idx'] - b1['idx']) < min_days:
                continue
            gap = b2['rsi'] - b1['rsi']
            if gap < min_gap:
                continue
            if b2['price'] > b1['price'] * 1.05:
                continue
            return {
                'ok': True,
                'b1_rsi': round(b1['rsi'], 1),
                'b2_rsi': round(b2['rsi'], 1),
                'gap': round(gap, 1),
                'b1_date': pd.Timestamp(b1['date']).strftime('%d/%m'),
                'b2_date': pd.Timestamp(b2['date']).strftime('%d/%m'),
                'rsi_now': round(rsi.iloc[-1], 1),
            }
    return None


def check_volume_dryup(df, dry_ratio=0.45):
    """Volume cạn kiệt dưới MA20"""
    vol = df['volume']
    if vol.sum() <= 0 or len(vol) < 30:
        return None
    ma20 = vol.rolling(20).mean().iloc[-1]
    if not ma20 or ma20 <= 0:
        return None
    ratio_last = vol.iloc[-1] / ma20
    ratio_3d = vol.iloc[-3:].mean() / ma20
    ratio = min(ratio_last, ratio_3d)
    return {'ok': ratio <= dry_ratio, 'ratio': round(ratio, 2),
            'vol_last': vol.iloc[-1], 'vol_ma20': ma20}


@st.cache_data(ttl=900, show_spinner=False)
def _analyze_ticker(ticker, days, max_rsi, min_gap, dry_ratio, max_pos):
    try:
        df = get_stock_data(ticker, days_back=days)
        if df is None or df.empty:
            return None
        df = _normalize(df)
        if len(df) < 150 or 'volume' not in df.columns:
            return None
        val = check_valuation_129(df, max_position=max_pos)
        rsi2 = check_rsi_double_bottom(df, max_rsi_bottom=max_rsi, min_gap=min_gap)
        vol = check_volume_dryup(df, dry_ratio=dry_ratio)
        if not (val and val['ok'] and rsi2 and rsi2['ok'] and vol and vol['ok']):
            return None
        score = round(
            max(0.0, (max_pos - val['position'])) * 60
            + max(0.0, rsi2['gap']) * 1.5
            + max(0.0, (dry_ratio - vol['ratio'])) * 80
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
            'Vol hiện tại (tr)': round(vol['vol_last'] / 1e6, 2),
            'Vol TB20 (tr)': round(vol['vol_ma20'] / 1e6, 2),
            'Vị thế 129 ngày': val['position'],
            'Score': score,
        }
    except Exception:
        return None


# ══════════════════════════════════════════════
# 3. PORTFOLIO LOGIC
# ══════════════════════════════════════════════

def _calc_pl(i):
    buy = st.session_state.pv2_portfolio['buy_prices'][i]
    cur = st.session_state.pv2_portfolio['current_prices'][i]
    if buy > 0 and cur > 0:
        return round(((cur - buy) / buy) * 100, 2)
    return 0.0


def _portfolio_summary():
    total = st.session_state.pv2_total_capital
    invested = 0
    cfg = st.session_state.pv2_portfolio
    for i in range(4):
        invested += cfg['quantities'][i] * cfg['current_prices'][i]
    cash = total - invested
    total_pl = sum(
        cfg['quantities'][i] * (cfg['current_prices'][i] - cfg['buy_prices'][i])
        for i in range(4) if cfg['buy_prices'][i] > 0
    )
    return {
        'total': total, 'invested': invested, 'cash': cash,
        'total_pl': total_pl,
        'cash_ratio': (cash / total * 100) if total > 0 else 0,
    }


def _suggest_trades(market_condition):
    cfg = st.session_state.pv2_portfolio
    suggestions = []
    if market_condition == 'XẤU':
        for i, stock in enumerate(cfg['stocks']):
            if cfg['status'][i] in ['MUA', 'GIỮ']:
                suggestions.append(('SELL_ALL', stock,
                                    '🚨 Thị trường xấu → bán hết, chuyển sang CHỜ', 'CAO'))
        return suggestions
    for i, stock in enumerate(cfg['stocks']):
        pl = _calc_pl(i)
        if pl < -5:
            suggestions.append(('CUT_LOSS', stock,
                                f'⚠️ Lỗ {pl:.1f}% → cắt lỗ hoặc hạ tỷ lệ', 'CAO'))
        elif pl > 15:
            suggestions.append(('TAKE_PROFIT', stock,
                                f'🎯 Lãi {pl:.1f}% → có thể chốt 50%', 'TRUNG BÌNH'))
    if market_condition == 'TỐT':
        best, best_pl = None, -999
        for i, stock in enumerate(cfg['stocks']):
            pl = _calc_pl(i)
            if pl > best_pl and pl > 0:
                best_pl = pl
                best = stock
        if best:
            suggestions.append(('INCREASE', best,
                                f'📈 Mã mạnh nhất ({best_pl:.1f}%) — có thể tăng tỷ lệ', 'THẤP'))
    return suggestions


def _push_top4_to_portfolio(top4):
    allocs = [40, 30, 20, 10]
    cfg = st.session_state.pv2_portfolio
    for i, r in enumerate(top4[:4]):
        cfg['stocks'][i]         = r['Mã CP']
        cfg['allocations'][i]    = allocs[i]
        cfg['status'][i]         = 'MUA'
        cfg['current_prices'][i] = r['Giá']
        cfg['buy_prices'][i]     = 0.0
        cfg['quantities'][i]     = 0
        cfg['notes'][i] = (
            f"Điểm mua vàng: RSI {r['RSI đáy 1']}→{r['RSI đáy 2']} "
            f"({r['Ngày đáy 1']}→{r['Ngày đáy 2']}), "
            f"vol {r['Vol/MA20']}x MA20, vị thế {int(r['Vị thế 129 ngày']*100)}%/129d"
        )
    cfg['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")


# ══════════════════════════════════════════════
# 4. GIAO DIỆN TAB — GỘP CẢ 2 PHẦN
# ══════════════════════════════════════════════

def render_portfolio_v2_tab(priority_tickers=None):
    _init_state()

    st.markdown("## 💼 SĂN ĐIỂM MUA VÀNG & QUẢN LÝ DANH MỤC 4 MÃ")
    st.caption(
        "**Luồng làm việc:** Quét cổ phiếu theo 3 điều kiện → "
        "Chọn 4 mã đẹp nhất (10-20-30-40%) → Theo dõi lãi/lỗ → "
        "Cắt lỗ / Chốt lời / Chờ khi thị trường xấu"
    )

    st.divider()

    # ═══════════════════════════════════════
    # PHẦN TRÊN: SCREENER
    # ═══════════════════════════════════════
    st.markdown("### 🎯 PHẦN 1 — SCREENER ĐIỂM MUA VÀNG")

    with st.expander("⚙️ Cấu hình bộ lọc (nhấn để điều chỉnh ngưỡng)", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        max_position  = c1.slider("📉 Vùng giá rẻ 129d ≤", 0.10, 0.60, 0.35, 0.05,
                                   help="Giá nằm trong vùng dưới 35% biên độ 129 phiên = rẻ")
        max_rsi       = c2.slider("🔻 RSI coi là đáy ≤", 25.0, 45.0, 35.0, 1.0)
        min_rsi_gap   = c3.slider("📐 Đáy 2 cao hơn đáy 1 tối thiểu", 1.0, 10.0, 2.0, 0.5)
        dry_ratio     = c4.slider("🥵 Volume cạn ≤ (× MA20)", 0.20, 0.80, 0.45, 0.05)

    custom = st.text_input(
        "🏷️ Danh sách mã quét (để trống = dùng danh sách ưu tiên VN30 của app)",
        placeholder="VD: PVT, FPT, HPG, VCB ...", value="",
        key="pv2_custom_input",
    )
    tickers = [t.strip().upper() for t in custom.replace(',', ' ').split()] if custom.strip() \
              else list(priority_tickers or [])

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        scan_clicked = st.button("🎯 QUÉT ĐIỂM MUA", type="primary", use_container_width=True)

    if scan_clicked:
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
                state="complete",
                expanded=bool(results),
            )
        st.session_state.pv2_scan_results = sorted(
            results, key=lambda x: x['Score'], reverse=True)

    # ═══════════════════════════════════════
    # KẾT QUẢ QUÉT + GỢI Ý 4 MÃ
    # ═══════════════════════════════════════
    results = st.session_state.pv2_scan_results
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"🏆 Tìm thấy **{len(results)}** mã đạt cả 3 điều kiện")

        with st.expander("📋 Bảng chi tiết (nhấn để mở)", expanded=True):
            st.dataframe(
                df_res, use_container_width=True, hide_index=True,
                column_config={
                    'Vị thế 129 ngày': st.column_config.ProgressColumn(
                        "Vị thế 129d", min_value=0.0, max_value=1.0, format="%.0f%%"),
                    'Vol/MA20': st.column_config.NumberColumn("Vol/MA20", format="%.2f x"),
                },
            )

        top4 = results[:4]
        st.markdown("#### 💡 Gợi ý 4 mã đẹp nhất (mã mạnh nhất → 40%)")

        allocs = [40, 30, 20, 10]
        rows = []
        for i, r in enumerate(top4):
            rows.append({
                'Slot': f"#{i+1}",
                'Mã CP': r['Mã CP'],
                'Tỷ lệ': f"{allocs[i]}%",
                'Giá': f"{r['Giá']:,.2f}",
                'RSI': f"{r['RSI đáy 1']} → {r['RSI đáy 2']}",
                'Vol': f"{r['Vol hiện tại (tr)']}tr / {r['Vol TB20 (tr)']}tr",
                'Điểm': r['Score'],
            })
        st.table(pd.DataFrame(rows))

        if st.button("📥 NẠP 4 MÃ VÀO PHẦN QUẢN LÝ DANH MỤC",
                     type="primary", use_container_width=True):
            _push_top4_to_portfolio(top4)
            st.success("✅ Đã nạp! Cuộn xuống **PHẦN 2** để nhập giá mua, số lượng và theo dõi.")
            st.rerun()

    else:
        st.info("Chưa quét hoặc chưa có mã nào đạt cả 3 điều kiện. "
                "Thử nới ngưỡng (vùng giá rẻ ↑, dry ratio ↑) rồi quét lại.")
        with st.expander("📖 Giải thích chiến lược + ví dụ PVT"):
            st.markdown("""
            **Ví dụ điểm mua PVT:**

            | Điều kiện | Thực tế | Đạt? |
            |---|---|---|
            | RSI 2 đáy nâng | Đáy 1 = 21 → Đáy 2 = 28 (giá không giảm thêm) | ✅ |
            | Volume kiệt cung | 1 triệu CP vs TB 20 phiên 3 triệu = 0.33x | ✅ |
            | Định giá rẻ 129d | Giá nằm ở vùng < 35% biên độ 129 phiên | ✅ |

            **Vì sao bộ 3 này mạnh?**
            - RSI đáy sau cao hơn đáy trước → *phe bán đã yếu* (phân kỳ dương)
            - Volume cạn → *không còn ai bán tháo*, cung đã kiệt
            - Giá vùng rẻ 129 ngày → *biên an toàn cao*, xuống ít – lên nhiều

            → Chỉ cần lực mua nhỏ xuất hiện là giá bật mạnh.
            """)

    st.divider()

    # ═══════════════════════════════════════
    # PHẦN DƯỚI: QUẢN LÝ DANH MỤC
    # ═══════════════════════════════════════
    st.markdown("### 💼 PHẦN 2 — QUẢN LÝ DANH MỤC 4 MÃ")

    col_h1, col_h2, col_h3 = st.columns([2, 1, 1])
    with col_h1:
        st.session_state.pv2_total_capital = st.number_input(
            "💰 Tổng vốn (VNĐ)",
            value=st.session_state.pv2_total_capital,
            step=1_000_000, format="%d", key="pv2_capital",
        )
    with col_h2:
        market_condition = st.selectbox(
            "📊 Đánh giá thị trường",
            ["TỐT", "TRUNG TÍNH", "XẤU"], key="pv2_mkt_cond",
        )
    with col_h3:
        st.caption(f"🕐 Cập nhật: {st.session_state.pv2_portfolio['last_updated']}")

    # ── Bảng tổng quan 4 slot ──
    cfg = st.session_state.pv2_portfolio
    rows = []
    for i in range(4):
        pl = _calc_pl(i)
        capital = st.session_state.pv2_total_capital * (cfg['allocations'][i] / 100)
        rows.append({
            'Slot': f"#{i+1}",
            'Mã CP': cfg['stocks'][i],
            'Tỷ lệ': f"{cfg['allocations'][i]}%",
            'Vốn (tr)': f"{capital/1e6:.1f}",
            'Trạng thái': cfg['status'][i],
            'Giá mua': f"{cfg['buy_prices'][i]:,.2f}" if cfg['buy_prices'][i] > 0 else '—',
            'Giá HT': f"{cfg['current_prices'][i]:,.2f}" if cfg['current_prices'][i] > 0 else '—',
            'SL': cfg['quantities'][i] if cfg['quantities'][i] > 0 else '—',
            'Lãi/Lỗ %': f"{pl:+.2f}%" if (cfg['buy_prices'][i] > 0 and cfg['current_prices'][i] > 0) else '—',
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Điều khiển chi tiết 4 slot ──
    st.markdown("#### 🎛️ Điều khiển từng slot (nhấn để mở)")
    cols = st.columns(2)
    for i in range(4):
        with cols[i % 2]:
            with st.expander(f"🔍 Slot #{i+1}: {cfg['stocks'][i]} ({cfg['allocations'][i]}%)"):
                new_stock = st.text_input("Mã CP", value=cfg['stocks'][i], key=f"pv2_s_{i}")

                c_a, c_b = st.columns(2)
                with c_a:
                    new_alloc = st.number_input(
                        "Tỷ lệ (%)", value=float(cfg['allocations'][i]),
                        min_value=0.0, max_value=100.0, step=5.0, key=f"pv2_a_{i}")
                with c_b:
                    new_status = st.selectbox(
                        "Trạng thái",
                        ["CHỜ", "MUA", "GIỮ", "BÁN"],
                        index=["CHỜ", "MUA", "GIỮ", "BÁN"].index(cfg['status'][i]),
                        key=f"pv2_st_{i}")

                c_c, c_d, c_e = st.columns(3)
                with c_c:
                    new_buy = st.number_input(
                        "Giá mua", value=float(cfg['buy_prices'][i]),
                        min_value=0.0, step=0.1, key=f"pv2_b_{i}")
                with c_d:
                    new_cur = st.number_input(
                        "Giá hiện tại", value=float(cfg['current_prices'][i]),
                        min_value=0.0, step=0.1, key=f"pv2_c_{i}")
                with c_e:
                    new_qty = st.number_input(
                        "Số lượng", value=cfg['quantities'][i],
                        min_value=0, step=100, key=f"pv2_q_{i}")

                new_note = st.text_input("Ghi chú", value=cfg['notes'][i], key=f"pv2_n_{i}")

                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    if st.button("💾 Lưu", key=f"pv2_save_{i}", use_container_width=True):
                        cfg['stocks'][i] = new_stock
                        cfg['allocations'][i] = int(new_alloc)
                        cfg['status'][i] = new_status
                        cfg['buy_prices'][i] = new_buy
                        cfg['current_prices'][i] = new_cur
                        cfg['quantities'][i] = new_qty
                        cfg['notes'][i] = new_note
                        cfg['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        st.success(f"✅ Đã lưu {new_stock}")
                        st.rerun()
                with bc2:
                    if st.button("🟢 MUA", key=f"pv2_buy_{i}", use_container_width=True):
                        cfg['status'][i] = 'MUA'
                        cfg['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        st.rerun()
                with bc3:
                    if st.button("🔴 CẮT LỖ", key=f"pv2_cut_{i}", use_container_width=True):
                        cfg['status'][i] = 'BÁN'
                        cfg['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        st.rerun()

    st.divider()

    # ── Tổng kết & Đề xuất ──
    st.markdown("### 📊 TỔNG KẾT & ĐỀ XUẤT")

    summary = _portfolio_summary()
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("💵 Tổng vốn", f"{summary['total']/1e6:.1f} Tr")
    col_s2.metric("📈 Đang đầu tư", f"{summary['invested']/1e6:.1f} Tr",
                  f"{(summary['invested']/summary['total']*100):.1f}%" if summary['total'] > 0 else None)
    col_s3.metric("💰 Tiền mặt", f"{summary['cash']/1e6:.1f} Tr",
                  f"{summary['cash_ratio']:.1f}%")
    col_s4.metric("💎 Lãi/Lỗ tổng", f"{summary['total_pl']/1e6:.2f} Tr")

    st.progress(
        summary['invested'] / summary['total'] if summary['total'] > 0 else 0,
        text=f"Đầu tư {summary['invested']/1e6:.1f} Tr · Tiền mặt {summary['cash']/1e6:.1f} Tr",
    )

    suggestions = _suggest_trades(market_condition)
    st.markdown("#### 💡 Đề xuất tự động")
    if suggestions:
        for t, stock, reason, prio in suggestions:
            if prio == 'CAO':
                st.error(f"**{stock}** — {reason}")
            elif prio == 'TRUNG BÌNH':
                st.warning(f"**{stock}** — {reason}")
            else:
                st.info(f"**{stock}** — {reason}")
    else:
        if market_condition == 'TỐT':
            st.success("✅ Danh mục ổn định — tiếp tục giữ và theo dõi")
        else:
            st.info("ℹ️ Thị trường trung tính — quan sát thêm")

    # ── Quy tắc hành động ──
    with st.expander("📖 Quy tắc Mua / Bán / Chờ (nhấn để đọc)"):
        st.markdown("""
        **🔴 BÁN KHI:**
        - Mã lỗ **> 5%** → cắt lỗ
        - Mã lãi **> 15%** → chốt 50%
        - **Thị trường XẤU** → bán toàn bộ 4 mã, chuyển sang CHỜ 100% tiền mặt
        - Bán mã xấu nhất, dùng vốn mua mã có tín hiệu TÍCH CỰC mạnh nhất

        **🟢 MUA KHI:**
        - Mã xuất hiện trong screener **ĐIỂM MUA VÀNG** (3 điều kiện đồng thời)
        - Thị trường TỐT, VN-Index trên MA20, thanh khoản tăng
        - Phân bổ theo tỷ lệ 10-20-30-40% (mã đẹp nhất → 40%)

        **⚪ CHỜ KHI:**
        - Thị trường giảm mạnh **> 5%** (PANIC)
        - Sau khi cắt lỗ, chờ tín hiệu mới
        - Giữ 100% tiền mặt trong 3-5 phiên, **không bắt đáy**
        - Quay lại khi có mã bứt phá với khối lượng lớn
        """)


if __name__ == "__main__":
    st.set_page_config(page_title="Portfolio v2", layout="wide")
    render_portfolio_v2_tab()
