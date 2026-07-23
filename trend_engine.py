import pandas as pd
import numpy as np

# ==================================================================================
# TREND ENGINE — Cỗ máy trạng thái Xu Hướng "Cô Tiên" (Tăng / Sideway / Giảm)
# Dùng cho tab Mô Phỏng (1 mã) và sau này cho backtester.py.
#
# KHÁC VỚI indicators.py: file đó chỉ soi NẾN CUỐI (snapshot) để quét nhanh
# hàng ngàn mã. File này ĐI QUA TỪNG PHIÊN LỊCH SỬ để dựng đúng state machine
# path-dependent như tài liệu mô tả:
#   "Kết thúc tăng qua sideway trước rồi mới sang giảm" — nghĩa là khi xu
#   hướng Tăng kết thúc, trạng thái luôn rơi về Sideway trước; chỉ từ Sideway
#   mới có thể bắt đầu một xu hướng Giảm mới (không có chuyện nhảy thẳng
#   Tăng -> Giảm trong cùng 1 phiên).
#
# ĐỊNH NGHĨA "MÂY" NỘI BỘ (giữ nguyên giả định đã thống nhất ở indicators.py):
#   Mây = dải giữa Knife1(65) và Knife2(129). Kijun(17) là đường xác nhận
#   nhanh so với mây đó (vai trò tương tự Kijun-sen gốc so với mây Senkou).
#   "Knife1(65) và Knife2(129) đồng thời trên mây và cùng đi lên" được hiểu
#   là: mây (chính do 2 đường này tạo ra) đang NGHIÊNG LÊN — tức Knife1 nằm
#   trên Knife2 và cả hai đều dốc lên. Nếu ý bạn là dùng mây Kumo cổ điển
#   riêng biệt, báo lại để đổi — nhưng lưu ý mây cổ điển đã test và gần như
#   không bao giờ thoả mãn cùng lúc với đường 129 (xem ghi chú indicators.py).
# ==================================================================================


def compute_fairy_engine(
    df,
    k17: int = 17, k65: int = 65, k129: int = 129,
    chikou_shift: int = 17,              # độ trễ Chikou = chu kỳ Kijun (17), không dùng 26 gốc
    hop_bich_threshold: float = 0.0014,  # Knife1&Knife2 lệch ≤0.14% => "hợp bích"
    khong_mua_duoi_pct: float = 3.0,     # giá chỉ được cách mây tối đa 3% mới coi là "chưa đuổi"
    vol_spike_normal: float = 1.75,      # chân sóng bình thường: 1.5-2x MA20 (lấy giữa)
    vol_spike_crisis: float = 2.5,       # đáy khủng hoảng: 2.5-3x MA20 (cố định theo yêu cầu)
    crisis_drawdown_pct: float = 20.0,   # sụt >=20% từ đỉnh gần nhất mới tính là "khủng hoảng"
    phan_phoi_pct_129: float = 30.0,     # giá vượt xa 129 ~30% + vol đột biến ~2x = vùng phân phối
    swing_window: int = 7,               # cửa sổ nhận diện đỉnh/đáy swing (xác nhận có độ trễ)
):
    """
    Trả về df đã có đầy đủ cột tính toán + cột 'Xu_Huong' (Tăng/Sideway/Giảm)
    đi qua từng phiên theo đúng state machine. Trả về None nếu dữ liệu quá ngắn.
    """
    min_len = k129 + max(swing_window, chikou_shift) + 10
    if df is None or len(df) < min_len:
        return None

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.reset_index(drop=True)

    # ------------------------------------------------------------------
    # 1. BA ĐƯỜNG ĐỊNH GIÁ + MÂY NỘI BỘ
    # ------------------------------------------------------------------
    df['kijun17'] = (df['high'].rolling(k17).max() + df['low'].rolling(k17).min()) / 2
    df['knife65'] = (df['high'].rolling(k65).max() + df['low'].rolling(k65).min()) / 2
    df['knife129'] = (df['high'].rolling(k129).max() + df['low'].rolling(k129).min()) / 2

    df['fmay_top'] = df[['knife65', 'knife129']].max(axis=1)
    df['fmay_bot'] = df[['knife65', 'knife129']].min(axis=1)

    df['kijun17_up'] = df['kijun17'] > df['kijun17'].shift(5)
    df['knife65_up'] = df['knife65'] > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    # ------------------------------------------------------------------
    # 2. VOLUME CƠ BẢN
    # ------------------------------------------------------------------
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ma60'] = df['volume'].rolling(60).mean()
    df['v_ratio'] = df['volume'] / df['vol_ma20']

    # ------------------------------------------------------------------
    # 3. ĐIỀU KIỆN BẮT ĐẦU TĂNG / GIẢM (cả 3 đường cùng hướng + mây nghiêng đúng chiều)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 4. CHIKOU SPAN — đường trễ, so sánh close[i] với mây tại vị trí (i - shift)
    # ------------------------------------------------------------------
    df['chikou_top_ref'] = df['fmay_top'].shift(chikou_shift)
    df['chikou_bot_ref'] = df['fmay_bot'].shift(chikou_shift)
    df['chikou_in_cloud'] = (df['close'] >= df['chikou_bot_ref']) & (df['close'] <= df['chikou_top_ref'])

    # ------------------------------------------------------------------
    # 5. ĐIỀU KIỆN KẾT THÚC TĂNG / GIẢM (2 cách tương đương, theo tài liệu)
    # ------------------------------------------------------------------
    cross_down_129 = (df['close'] <= df['knife129']) & (df['close'].shift(1) > df['knife129'].shift(1))
    cross_up_129 = (df['close'] >= df['knife129']) & (df['close'].shift(1) < df['knife129'].shift(1))

    df['end_uptrend'] = df['chikou_in_cloud'].fillna(False) | cross_down_129.fillna(False)
    df['end_downtrend'] = df['chikou_in_cloud'].fillna(False) | cross_up_129.fillna(False)

    # ------------------------------------------------------------------
    # 6. STATE MACHINE — đi qua từng phiên (bắt buộc Tăng->Sideway->Giảm, không nhảy cóc)
    # ------------------------------------------------------------------
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

    # Đánh dấu phiên đầu tiên của mỗi xu hướng mới (chân sóng) để gắn tín hiệu volume
    df['trend_start'] = (df['Xu_Huong'] != df['Xu_Huong'].shift(1)) & (df['Xu_Huong'] != "Sideway")

    # ------------------------------------------------------------------
    # 7. HỢP BÍCH & KHÔNG MUA ĐUỔI (2 bộ lọc tinh của xu hướng Tăng)
    # ------------------------------------------------------------------
    df['hop_bich'] = (abs(df['knife65'] - df['knife129']) / df['knife129']) <= hop_bich_threshold
    dist_above_may_pct = (df['close'] - df['fmay_top']) / df['fmay_top'] * 100
    df['khong_mua_duoi'] = (df['Xu_Huong'] == "Tăng") & (dist_above_may_pct <= khong_mua_duoi_pct) & (dist_above_may_pct >= 0)
    df['canh_bao_mua_duoi'] = (df['Xu_Huong'] == "Tăng") & (dist_above_may_pct > khong_mua_duoi_pct)

    # ------------------------------------------------------------------
    # 8. XÁC NHẬN KHỐI LƯỢNG CHO CHÂN SÓNG (đầu xu hướng Tăng)
    #    - Bình thường: >= 1.5-2 lần MA20 (lấy mốc 1.75x)
    #    - Đáy khủng hoảng (giá vừa sụt >=20% từ đỉnh gần nhất): >= 2.5x MA20
    # ------------------------------------------------------------------
    rolling_high_60 = df['close'].rolling(60).max()
    drawdown_pct = (rolling_high_60 - df['close']) / rolling_high_60 * 100
    df['la_day_khung_hoang'] = df['trend_start'] & (df['Xu_Huong'] == "Tăng") & (drawdown_pct.shift(1) >= crisis_drawdown_pct)

    required_vol_mult = np.where(df['la_day_khung_hoang'], vol_spike_crisis, vol_spike_normal)
    df['xac_nhan_chan_song'] = df['trend_start'] & (df['Xu_Huong'] == "Tăng") & (df['v_ratio'] >= required_vol_mult)

    # ------------------------------------------------------------------
    # 9. CẤU TRÚC "TĂNG KHỎE" — đáy sau cao hơn đáy trước, đỉnh sau cao hơn đỉnh trước
    #    LƯU Ý: đây là chỉ báo XÁC NHẬN CÓ ĐỘ TRỄ (dùng cửa sổ 2 chiều để nhận
    #    diện swing), phù hợp để tô màu/nhận định trên biểu đồ lịch sử, KHÔNG
    #    dùng làm tín hiệu vào lệnh real-time.
    # ------------------------------------------------------------------
    is_swing_high = df['high'] == df['high'].rolling(swing_window, center=True).max()
    is_swing_low = df['low'] == df['low'].rolling(swing_window, center=True).min()

    # Với mỗi điểm swing, lấy giá trị swing NGAY TRƯỚC nó (để so sánh "sau cao hơn trước"),
    # rồi forward-fill ra toàn bộ df để mỗi phiên đều biết 2 swing gần nhất là bao nhiêu.
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

    # ------------------------------------------------------------------
    # 10. CẢNH BÁO TẠO ĐỈNH / PHÂN PHỐI
    #     - Tạo đỉnh: giá lập đỉnh N phiên nhưng volume đang kiệt dần (phân kỳ).
    #     - Phân phối: 1 cây volume đột biến ~2x MA20 ngay tại đỉnh + giá vượt
    #       xa Knife2(129) ~30% (tài liệu ghi mốc này theo khung TUẦN — ở đây
    #       áp trực tiếp ngưỡng % lên dữ liệu ngày như một xấp xỉ đơn giản hoá,
    #       có thể cần hiệu chỉnh nếu bạn muốn tính đúng khung tuần).
    # ------------------------------------------------------------------
    near_20d_high = df['close'] >= df['close'].rolling(20).max() * 0.97
    df['canh_bao_tao_dinh'] = near_20d_high & (df['v_ratio'] < 0.7)

    pct_vs_129 = (df['close'] - df['knife129']) / df['knife129'] * 100
    df['pct_vs_129'] = pct_vs_129
    df['vung_phan_phoi'] = near_20d_high & (df['v_ratio'] >= 2.0) & (pct_vs_129 >= phan_phoi_pct_129)

    return df


def get_latest_snapshot(df_engine: pd.DataFrame) -> dict:
    """Tóm tắt trạng thái phiên mới nhất — dùng để hiển thị metric trên tab Mô Phỏng."""
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
    # trend_engine.py  →  thêm hàm này vào cuối file

# trend_engine.py — sửa hàm market_recommendation

def market_recommendation(snap: dict, pe_stats: dict = None) -> dict:
    """
    Khuyến nghị tổng hợp:
    - Trend + Volume + RSI + MACD (đã có)
    - + P/E percentile (MỚI)
    """
    score, reasons = 0, []

    # ===== TREND =====
    t = snap["trend_text"]
    if "tăng mạnh" in t:
        score += 2; reasons.append("✅ Xu hướng tăng mạnh — nên duy trì/vào thêm")
    elif "chậm lại" in t:
        score += 1; reasons.append("↗️ Tăng chậm lại — giữ, không mua đuổi")
    elif "gãy MA20" in t:
        score -= 1; reasons.append("⚠️ Vừa gãy MA20 — cân nhắc giảm tỷ trọng")
    else:
        score -= 2; reasons.append("📉 Xu hướng giảm — nên giảm tỷ trọng")

    # ===== RSI =====
    rsi = snap["rsi"]
    if rsi >= 70:
        score -= 1; reasons.append(f"🔴 RSI={rsi} quá mua — chốt lời một phần")
    elif rsi <= 30:
        score += 1; reasons.append(f"🟢 RSI={rsi} quá bán — cơ hội tích lũy dần")
    else:
        reasons.append(f"🟡 RSI={rsi} trung tính — quan sát thêm")

    # ===== MACD =====
    if snap["macd_cross"] == "Vàng":
        score += 1; reasons.append("✅ MACD cắt lên — tín hiệu tích cực")
    else:
        score -= 1; reasons.append("⚠️ MACD cắt xuống — tín hiệu tiêu cực")

    # ===== VOLUME =====
    vr = snap["vol_ratio"]
    if vr >= 1.5:
        reasons.append(f"🔥 Volume đột biến {vr}x — dòng tiền hỗ trợ")
    elif vr < 0.7:
        score -= 1; reasons.append(f"💤 Volume yếu {vr}x — thiếu dòng tiền")

    # ===== P/E VALUATION (MỚI) =====
    if pe_stats and pe_stats.get("percentile") is not None:
        pct = pe_stats["percentile"]
        z   = pe_stats.get("zscore", 0)
        if pct < 15:
            score += 2
            reasons.append(f"💰 P/E={pe_stats['pe_now']:.1f}x ở percentile {pct:.0f}% — RẺ kỷ lục, cơ hội tích lũy")
        elif pct < 30:
            score += 1
            reasons.append(f"💰 P/E percentile {pct:.0f}% — vùng rẻ, ưu tiên mua gom")
        elif pct > 85:
            score -= 2
            reasons.append(f"💰 P/E percentile {pct:.0f}% — ĐẮT, nên chốt lời dần")
        elif pct > 70:
            score -= 1
            reasons.append(f"💰 P/E percentile {pct:.0f}% — vùng đắt, hạn chế mua mới")
        else:
            reasons.append(f"💰 P/E percentile {pct:.0f}% — định giá hợp lý")

    # ===== PHÂN BỔ =====
    if score >= 4:
        stock, cash, action, color = 75, 25, "🚀 MUA MẠNH - VÙNG ĐẸP", "success"
    elif score >= 2:
        stock, cash, action, color = 65, 35, "🟢 MUA / GIỮ TỶ TRỌNG CAO", "success"
    elif score >= 0:
        stock, cash, action, color = 50, 50, "➖ GIỮ - CÂN BẰNG", "info"
    elif score >= -2:
        stock, cash, action, color = 35, 65, "⚠️ GIẢM TỶ TRỌNG", "warning"
    else:
        stock, cash, action, color = 20, 80, "🛡️ PHÒNG THỦ - GIỮ TIỀN MẶT", "danger"

    return {
        "score": score, "action": action, "stock": stock,
        "cash": cash, "color": color, "reasons": reasons,
    }
