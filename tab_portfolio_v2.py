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
        for i in range(4) if cfg['
