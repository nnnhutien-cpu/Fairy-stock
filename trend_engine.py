import pandas as pd
import numpy as np

# ==================================================================================
# TREND ENGINE — Cỗ máy trạng thái Xu Hướng "Cô Tiên"
# ==================================================================================

def compute_fairy_engine(
    df,
    k17: int = 17, k65: int = 65, k129: int = 129,
    chikou_shift: int = 17,
    hop_bich_threshold: float = 0.0014,
    khong_mua_duoi_pct: float = 3.0,
    vol_spike_normal: float = 1.75,
    vol_spike_crisis: float = 2.5,
    crisis_drawdown_pct: float = 20.0,
    phan_phoi_pct_129: float = 30.0,
    swing_window: int = 7,
):
    min_len = k129 + max(swing_window, chikou_shift) + 10
    if df is None or len(df) < min_len:
        return None

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.reset_index(drop=True)

    df['kijun17'] = (df['high'].rolling(k17).max() + df['low'].rolling(k17).min()) / 2
    df['knife65'] = (df['high'].rolling(k65).max() + df['low'].rolling(k65).min()) / 2
    df['knife129'] = (df['high'].rolling(k129).max() + df['low'].rolling(k129).min()) / 2

    df['fmay_top'] = df[['knife65', 'knife129']].max(axis=1)
    df['fmay_bot'] = df[['knife65', 'knife129']].min(axis=1)

    df['kijun17_up'] = df['kijun17'] > df['kijun17'].shift(5)
    df['knife65_up'] = df['knife65'] > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ma60'] = df['volume'].rolling(60).mean()
    df['v_ratio'] = df['volume'] / df['vol_ma20']

    knife_core_up = (df['knife65'] > df['knife129']) & df['knife65_up'] & df['knife129_up']
    knife_core_down = (df['knife65'] < df['knife129']) & ~df['knife65_up'] & ~df['knife129_up']

    df['up_condition'] = (
        knife_core_up
        & (df['kijun17'] > df['fmay_top']) & df['kijun17_up']
        & (df['close'] > df['fmay_top'])
    )
    df['down_condition'] = (
        knife_core_down
        & (df['kijun17'] < df['fmay_bot']) & ~df['kijun17_up']
        & (df['close'] < df['fmay_bot'])
    )

    df['chikou_top_ref'] = df['fmay_top'].shift(chikou_shift)
    df['chikou_bot_ref'] = df['fmay_bot'].shift(chikou_shift)
    df['chikou_in_cloud'] = (df['close'] >= df['chikou_bot_ref']) & (df['close'] <= df['chikou_top_ref'])

    cross_down_129 = (df['close'] <= df['knife129']) & (df['close'].shift(1) > df['knife129'].shift(1))
    cross_up_129 = (df['close'] >= df['knife129']) & (df['close'].shift(1) < df['knife129'].shift(1))

    df['end_uptrend'] = df['chikou_in_cloud'].fillna(False) | cross_down_129.fillna(False)
    df['end_downtrend'] = df['chikou_in_cloud'].fillna(False) | cross_up_129.fillna(False)

    states = []
    state = "Sideway"
    for i in range(len(df)):
        up_ok = bool(df['up_condition'].iloc[i]) if pd.notna(df['up_condition'].iloc[i]) else False
        down_ok = bool(df['down_condition'].iloc[i]) if pd.notna(df['down_condition'].iloc[i]) else False
        end_up = bool(df['end_uptrend'].iloc[i])
        end_dn = bool(df['end_downtrend'].iloc[i])

        if state == "Sideway":
            if up_ok:
                state = "Tăng"
            elif down_ok:
                state = "Giảm"
        elif state == "Tăng":
            if end_up:
                state = "Sideway"
        elif state == "Giảm":
            if end_dn:
                state = "Sideway"
        states.append(state)
    df['Xu_Huong'] = states

    df['trend_start'] = (df['Xu_Huong'] != df['Xu_Huong'].shift(1)) & (df['Xu_Huong'] != "Sideway")

    df['hop_bich'] = (abs(df['knife65'] - df['knife129']) / df['knife129']) <= hop_bich_threshold
    dist_above_may_pct = (df['close'] - df['fmay_top']) / df['fmay_top'] * 100
    df['khong_mua_duoi'] = (df['Xu_Huong'] == "Tăng") & (dist_above_may_pct <= khong_mua_duoi_pct) & (dist_above_may_pct >= 0)
    df['canh_bao_mua_duoi'] = (df['Xu_Huong'] == "Tăng") & (dist_above_may_pct > khong_mua_duoi_pct)

    rolling_high_60 = df['close'].rolling(60).max()
    drawdown_pct = (rolling_high_60 - df['close']) / rolling_high_60 * 100
    df['la_day_khung_hoang'] = df['trend_start'] & (df['Xu_Huong'] == "Tăng") & (drawdown_pct.shift(1) >= crisis_drawdown_pct)

    required_vol_mult = np.where(df['la_day_khung_hoang'], vol_spike_crisis, vol_spike_normal)
    df['xac_nhan_chan_song'] = df['trend_start'] & (df['Xu_Huong'] == "Tăng") & (df['v_ratio'] >= required_vol_mult)

    is_swing_high = df['high'] == df['high'].rolling(swing_window, center=True).max()
    is_swing_low = df['low'] == df['low'].rolling(swing_window, center=True).min()

    swing_high_only = df.loc[is_swing_high, 'high']
    prev_high_at_swing = swing_high_only.shift(1)
    df['prev_swing_high_val'] = np.nan
    df.loc[is_swing_high, 'prev_swing_high_val'] = prev_high_at_swing.values
    df['prev_swing_high_val'] = df['prev_swing_high_val'].ffill()
    df['last_swing_high_val'] = df['high'].where(is_swing_high).ffill()

    swing_low_only = df.loc[is_swing_low, 'low']
    prev_low_at_swing = swing_low_only.shift(1)
    df['prev_swing_low_val'] = np.nan
    df.loc[is_swing_low, 'prev_swing_low_val'] = prev_low_at_swing.values
    df['prev_swing_low_val'] = df['prev_swing_low_val'].ffill()
    df['last_swing_low_val'] = df['low'].where(is_swing_low).ffill()

    df['dinh_sau_cao_hon'] = df['last_swing_high_val'] > df['prev_swing_high_val']
    df['day_sau_cao_hon'] = df['last_swing_low_val'] > df['prev_swing_low_val']
    df['cau_truc_khoe'] = (
        (df['Xu_Huong'] == "Tăng")
        & df['dinh_sau_cao_hon'].fillna(False)
        & df['day_sau_cao_hon'].fillna(False)
        & (df['vol_ma20'] >= df['vol_ma60'])
    )

    near_20d_high = df['close'] >= df['close'].rolling(20).max() * 0.97
    df['canh_bao_tao_dinh'] = near_20d_high & (df['v_ratio'] < 0.7)

    pct_vs_129 = (df['close'] - df['knife129']) / df['knife129'] * 100
    df['pct_vs_129'] = pct_vs_129
    df['vung_phan_phoi'] = near_20d_high & (df['v_ratio'] >= 2.0) & (pct_vs_129 >= phan_phoi_pct_129)

    return df


def get_latest_snapshot(df_engine) -> dict:
    if df_engine is None or df_engine.empty:
        return {}
    last = df_engine.iloc[-1]
    return {
        "xu_huong": last['Xu_Huong'],
        "kijun17": round(last['kijun17'], 2),
        "knife65": round(last['knife65'], 2),
        "knife129": round(last['knife129'], 2),
        "pct_vs_129": round(last['pct_vs_129'], 2) if pd.notna(last.get('pct_vs_129')) else None,
        "hop_bich": bool(last['hop_bich']),
        "khong_mua_duoi": bool(last['khong_mua_duoi']),
        "canh_bao_mua_duoi": bool(last['canh_bao_mua_duoi']),
        "cau_truc_khoe": bool(last['cau_truc_khoe']),
        "canh_bao_tao_dinh": bool(last['canh_bao_tao_dinh']),
        "vung_phan_phoi": bool(last['vung_phan_phoi']),
        "v_ratio": round(last['v_ratio'], 2) if pd.notna(last.get('v_ratio')) else None,
    }


def market_recommendation(snap: dict, pe_stats: dict = None,
                          breadth: dict = None) -> dict:
    """
    Khuyến nghị dựa trên:
    - Layer 1: Breadth (A/D từ HOSE)     → -5 đến +5
    - Layer 2: PTKT (Trend, RSI, MACD)   → -4 đến +4
    - Layer 3: P/E                       → -2 đến +2
    ----------------------------------------------
    TỔNG SCORE: -11 đến +11
    """
    score, reasons = 0, []

    # ========================================================
    # LAYER 1: BREADTH (A/D ratio từ ~400 mã HOSE)
    # ========================================================
    ad_pct = None
    adv = dec = 0
    if breadth and breadth.get("total", 0) > 0:
        adv = breadth.get("advance", 0)
        dec = breadth.get("decline", 0)
        total = breadth.get("total", adv + dec)
        ad_pct = adv / max(total, 1) * 100
        avg_chg = breadth.get("ad_change", 0)

        if ad_pct > 70:
            score += 5
            reasons.append(f"🟢 Breadth RẤT MẠNH ({adv}/{dec} - {ad_pct:.0f}% mã tăng)")
        elif ad_pct > 60:
            score += 4
            reasons.append(f"🟢 Breadth MẠNH ({adv}/{dec} - {ad_pct:.0f}% mã tăng)")
        elif ad_pct > 50:
            score += 3
            reasons.append(f"🟢 Breadth KHÁ ({adv}/{dec} - {ad_pct:.0f}% mã tăng)")
        elif ad_pct > 40:
            score += 1
            reasons.append(f"🟡 Breadth TRUNG TÍNH ({adv}/{dec} - {ad_pct:.0f}%)")
        elif ad_pct > 30:
            score -= 1
            reasons.append(f"🟠 Breadth YẾU ({adv}/{dec} - chỉ {ad_pct:.0f}% mã tăng)")
        elif ad_pct > 20:
            score -= 3
            reasons.append(f"🟠 Breadth RẤT YẾU ({adv}/{dec} - {ad_pct:.0f}%)")
        else:
            score -= 5
            reasons.append(f"🔴 Breadth PANIC ({adv}/{dec} - {ad_pct:.0f}% - thị trường sụp)")

    # ========================================================
    # LAYER 2: PTKT
    # ========================================================
    # TREND
    t = snap.get("trend_text", "")
    if "tăng mạnh" in t:
        score += 2
        reasons.append("📈 Trend tăng mạnh (giá trên MA20 + MA20 dốc lên)")
    elif "chậm lại" in t:
        score += 1
        reasons.append("↗️ Trend tăng chậm lại")
    elif "gãy MA20" in t:
        score -= 1
        reasons.append("⚠️ Vừa gãy MA20")
    else:
        score -= 2
        reasons.append("📉 Trend giảm")

    # RSI
    rsi = snap.get("rsi", 50)
    if rsi >= 70:
        score -= 1
        reasons.append(f"🔴 RSI={rsi} quá mua")
    elif rsi <= 30:
        score += 1
        reasons.append(f"🟢 RSI={rsi} quá bán - cơ hội")
    else:
        reasons.append(f"🟡 RSI={rsi} trung tính")

    # MACD
    if snap.get("macd_cross") == "Vàng":
        score += 1
        reasons.append("✅ MACD vàng (cắt lên)")
    else:
        score -= 1
        reasons.append("⚠️ MACD chết (cắt xuống)")

    # VOLUME
    vol_ratio = snap.get("vol_ratio", 1)
    if vol_ratio >= 1.5:
        score += 1
        reasons.append(f"🔥 Volume đột biến {vol_ratio}x")
    elif vol_ratio < 0.7:
        score -= 1
        reasons.append(f"💤 Volume yếu {vol_ratio}x")

    # ========================================================
    # LAYER 3: P/E
    # ========================================================
    if pe_stats and pe_stats.get("percentile") is not None:
        pct = pe_stats["percentile"]
        if pct < 20:
            score += 2
            reasons.append(f"💰 P/E rẻ kỷ lục (percentile {pct:.0f}%)")
        elif pct < 30:
            score += 1
            reasons.append(f"💰 P/E vùng rẻ (percentile {pct:.0f}%)")
        elif pct > 80:
            score -= 2
            reasons.append(f"💰 P/E đắt kỷ lục (percentile {pct:.0f}%)")
        elif pct > 70:
            score -= 1
            reasons.append(f"💰 P/E vùng đắt (percentile {pct:.0f}%)")
        else:
            reasons.append(f"💰 P/E hợp lý (percentile {pct:.0f}%)")

    # ========================================================
    # TỔNG SCORE → TỶ TRỌNG (12 MỨC)
    # ========================================================
    if score >= 9:
        stock, cash, action, color = 80, 20, "🔥 MUA RẤT MẠNH", "success"
    elif score >= 7:
        stock, cash, action, color = 70, 30, "🚀 MUA MẠNH", "success"
    elif score >= 5:
        stock, cash, action, color = 65, 35, "🟢 MUA TÍCH CỰC", "success"
    elif score >= 3:
        stock, cash, action, color = 60, 40, "🟢 MUA/GIỮ", "success"
    elif score >= 1:
        stock, cash, action, color = 55, 45, "🟢 GIỮ TỶ TRỌNG CAO", "info"
    elif score >= -1:
        stock, cash, action, color = 50, 50, "➖ CÂN BẰNG", "info"
    elif score >= -3:
        stock, cash, action, color = 40, 60, "🟠 GIẢM NHẸ", "warning"
    elif score >= -5:
        stock, cash, action, color = 30, 70, "⚠️ GIẢM TỶ TRỌNG", "warning"
    elif score >= -7:
        stock, cash, action, color = 20, 80, "🔴 PHÒNG THỦ", "danger"
    elif score >= -9:
        stock, cash, action, color = 15, 85, "🛡️ PHÒNG THỦ MẠNH", "danger"
    else:
        stock, cash, action, color = 10, 90, "💀 THOÁT KHỎI THỊ TRƯỜNG", "danger"

    return {
        "score":        score,
        "action":       action,
        "stock":        stock,
        "cash":         cash,
        "color":        color,
        "reasons":      reasons,
        "ad_pct":       ad_pct,
        "ad_advance":   adv,
        "ad_decline":   dec,
    }
