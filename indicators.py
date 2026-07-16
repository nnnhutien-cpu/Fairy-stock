import streamlit as st
import pandas as pd
import numpy as np

# ==================================================================================
# HỆ THỐNG "CÔ TIÊN" — 3 ĐƯỜNG ĐỊNH GIÁ Kijun17 / Knife1(65) / Knife2(129)
# theo tài liệu triết lý giao dịch (đường 129 là quan trọng nhất).
#
# ĐỊNH NGHĨA "MÂY" NỘI BỘ (ghi chú minh bạch — báo lại nếu hiểu sai ý bạn):
#   Tài liệu vừa nói "vứt bỏ mây Ichimoku, chỉ dùng đường 129" (mục 2) vừa nói
#   "3 đường cùng nằm TRÊN MÂY" (bảng kỹ thuật) — hai câu chỉ nhất quán nếu
#   "mây" được hiểu là dải nằm giữa Knife1(65) và Knife2(129) (đóng vai trò
#   Senkou A/B của hệ mới), còn Kijun(17) đóng vai trò xác nhận nhanh so với
#   dải đó — TƯƠNG TỰ vai trò Tenkan/Kijun so với mây Senkou gốc.
#   Đã thử bằng dữ liệu giả lập: nếu dùng mây Kumo CỔ ĐIỂN (Tenkan9/Kijun26/
#   SenkouB52, dịch 26) làm chuẩn so sánh, Knife2-129 gần như KHÔNG BAO GIỜ
#   vượt được mây kể cả trong xu hướng tăng rất sạch (cửa sổ 129 phiên luôn
#   "kéo" đường xuống thấp hơn cửa sổ ngắn hơn của mây cổ điển).
#   => Mây cổ điển vẫn được TÍNH và hiển thị (cột "Ichimoku_Cloud") để tham
#      khảo, nhưng KHÔNG dùng để xác định Xu Hướng nữa.
#
# QUY TẮC:
#   - Mây nội bộ = dải [Knife129, Knife65] (lấy min/max, không cố định thứ tự).
#   - TĂNG: Knife65 > Knife129 (mây dốc lên) + cả 2 cùng đi lên (QUAN TRỌNG NHẤT)
#           + Kijun17 trên mây và đang đi lên + giá đóng cửa trên mây.
#   - GIẢM: đối xứng hoàn toàn.
#   - KẾT THÚC xu hướng: giá đóng cửa cắt qua Knife2(129) — đường định giá
#     quan trọng nhất, dùng làm mốc "chốt" chính theo đúng tinh thần tài liệu.
#   - MFI(14) & RSI(14) CHỈ dùng làm tín hiệu mua/bán khi đang Sideway.
#   - Tín hiệu "Bắt Đáy": giá chiết khấu sâu về sát/dưới Knife2-129 CỘNG khối
#     lượng đột biến >= 2.5 lần trung bình 20 phiên (ngưỡng cố định theo yêu
#     cầu người dùng).
#
# LƯU Ý: Đây là bộ lọc CẮT LÁT (snapshot) cho hàng loạt mã cùng lúc — "Xu
# Hướng" suy ra từ điều kiện nến MỚI NHẤT, không phải state-machine đi qua
# từng phiên lịch sử (việc đó dành cho backtester.py ở bước kế tiếp).
# ==================================================================================


@st.cache_data(show_spinner=False)
def calculate_technical_signals(
    df, ticker,
    p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26,   # mây Kumo cổ điển
    k17=17, k65=65, k129=129,                             # 3 đường định giá "Cô Tiên"
    vol_spike_mult=2.5,                                   # ngưỡng bắt đáy: 2.5x MA20
    hop_bich_threshold=0.0014,                            # "hợp bích": Knife1&Knife2 lệch ≤0.14%
):
    min_len = max(p_senkou_b + p_shift, k129) + 10
    if df is None or len(df) < min_len:
        return None

    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # ------------------------------------------------------------------
    # 1. THANH KHOẢN & MA CƠ BẢN
    # ------------------------------------------------------------------
    df['vol_ma20'] = df['volume'].rolling(20).mean()

    # ------------------------------------------------------------------
    # 2. RSI(14) — chỉ dùng khi Sideway (theo tài liệu)
    # ------------------------------------------------------------------
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi14'] = 100 - (100 / (1 + (gain / loss)))

    # ------------------------------------------------------------------
    # 3. MFI(14) — chỉ dùng khi Sideway (theo tài liệu, tách biệt RSI)
    # ------------------------------------------------------------------
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    raw_money_flow = typical_price * df['volume']
    tp_diff = typical_price.diff()
    pos_flow = raw_money_flow.where(tp_diff > 0, 0.0).rolling(14).sum()
    neg_flow = raw_money_flow.where(tp_diff < 0, 0.0).rolling(14).sum()
    money_ratio = pos_flow / neg_flow.replace(0, np.nan)
    df['mfi14'] = 100 - (100 / (1 + money_ratio))

    # ------------------------------------------------------------------
    # 4. MÂY KUMO CỔ ĐIỂN (giữ nguyên làm khung xác nhận xu hướng gốc)
    # ------------------------------------------------------------------
    df['tenkan'] = (df['high'].rolling(p_tenkan).max() + df['low'].rolling(p_tenkan).min()) / 2
    df['kijun26'] = (df['high'].rolling(p_kijun).max() + df['low'].rolling(p_kijun).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun26']) / 2).shift(p_shift)
    df['senkou_b'] = ((df['high'].rolling(p_senkou_b).max() + df['low'].rolling(p_senkou_b).min()) / 2).shift(p_shift)
    df['cloud_top'] = df[['senkou_a', 'senkou_b']].max(axis=1)
    df['cloud_bot'] = df[['senkou_a', 'senkou_b']].min(axis=1)

    # ------------------------------------------------------------------
    # 5. BA ĐƯỜNG ĐỊNH GIÁ "CÔ TIÊN" — KHÔNG dịch, công thức (HHV+LLV)/2
    # ------------------------------------------------------------------
    df['kijun17'] = (df['high'].rolling(k17).max() + df['low'].rolling(k17).min()) / 2
    df['knife65'] = (df['high'].rolling(k65).max() + df['low'].rolling(k65).min()) / 2
    df['knife129'] = (df['high'].rolling(k129).max() + df['low'].rolling(k129).min()) / 2

    # Hướng đi (so với chính nó N phiên trước) của từng đường — dùng 5 phiên để lọc nhiễu
    df['kijun17_up'] = df['kijun17'] > df['kijun17'].shift(5)
    df['knife65_up'] = df['knife65'] > df['knife65'].shift(5)
    df['knife129_up'] = df['knife129'] > df['knife129'].shift(5)

    # ------------------------------------------------------------------
    # 6. MÂY NỘI BỘ "CÔ TIÊN" = dải giữa Knife1(65) và Knife2(129)
    # ------------------------------------------------------------------
    df['fmay_top'] = df[['knife65', 'knife129']].max(axis=1)
    df['fmay_bot'] = df[['knife65', 'knife129']].min(axis=1)

    latest = df.iloc[-1]
    close = latest['close']

    if pd.isna(latest['fmay_top']) or pd.isna(latest['knife129']):
        return None

    # ------------------------------------------------------------------
    # 7. BỘ LỌC THANH KHOẢN >= 20 TỶ/PHIÊN
    # ------------------------------------------------------------------
    gtgd_ty = (close * (1000 if close < 500 else 1) * latest['volume']) / 1_000_000_000
    if gtgd_ty < 20:
        return None

    # ------------------------------------------------------------------
    # 8. VỊ TRÍ SO VỚI MÂY CỔ ĐIỂN
    # ------------------------------------------------------------------
    if close > latest['cloud_top']:
        cloud_status = "☁️ Trên Mây"
    elif close < latest['cloud_bot']:
        cloud_status = "🌧️ Dưới Mây"
    else:
        cloud_status = "🌫️ Trong Mây"

    # ------------------------------------------------------------------
    # 9. XU HƯỚNG THEO 3 ĐƯỜNG "CÔ TIÊN" (BẮT ĐẦU tăng/giảm — snapshot)
    #    Quan trọng nhất: Knife1(65) & Knife2(129) tạo mây nội bộ dốc lên/
    #    xuống và cùng đi lên/xuống. Kijun17 xác nhận thêm bằng cách đứng
    #    trên/dưới mây nội bộ đó và cùng hướng.
    # ------------------------------------------------------------------
    knife_core_up = latest['knife65'] > latest['knife129'] and latest['knife65_up'] and latest['knife129_up']
    knife_core_down = latest['knife65'] < latest['knife129'] and not latest['knife65_up'] and not latest['knife129_up']

    all3_up = (
        knife_core_up
        and latest['kijun17'] > latest['fmay_top'] and latest['kijun17_up']
        and close > latest['fmay_top']
    )
    all3_down = (
        knife_core_down
        and latest['kijun17'] < latest['fmay_bot'] and not latest['kijun17_up']
        and close < latest['fmay_bot']
    )

    # KẾT THÚC xu hướng: giá đóng cửa cắt qua Knife2(129) — đường định giá
    # quan trọng nhất theo tài liệu, dùng làm mốc chốt chính.
    end_uptrend = close <= latest['knife129']
    end_downtrend = close >= latest['knife129']

    if all3_up and not end_uptrend:
        xu_huong = "🟢 Tăng"
    elif all3_down and not end_downtrend:
        xu_huong = "🔴 Giảm"
    else:
        xu_huong = "🟡 Sideway"

    # "Hợp bích": Knife1(65) & Knife2(129) hội tụ sát nhau -> tích lũy trước bùng nổ
    hop_bich = abs(latest['knife65'] - latest['knife129']) / latest['knife129'] <= hop_bich_threshold

    # ------------------------------------------------------------------
    # 10. ĐỊNH GIÁ THEO ĐƯỜNG 129 — "rẻ" khi dưới/sát, "đắt" khi càng xa trên
    # ------------------------------------------------------------------
    pct_vs_129 = (close - latest['knife129']) / latest['knife129'] * 100
    if pct_vs_129 <= 0:
        dinh_gia = "📉 Rẻ (dưới/sát 129)"
    elif pct_vs_129 <= 15:
        dinh_gia = "⚖️ Hợp lý"
    else:
        dinh_gia = "📈 Đắt (mua bằng lòng tham)"

    # Cảnh báo "mua đuổi": giá đã đi quá xa trên mây/129 ngay từ đầu xu hướng
    canh_bao_mua_duoi = pct_vs_129 > 15

    # ------------------------------------------------------------------
    # 11. KHỐI LƯỢNG — Dòng tiền & tín hiệu Bắt Đáy (2.5x MA20, giá sát/dưới 129)
    # ------------------------------------------------------------------
    v_ratio = latest['volume'] / latest['vol_ma20'] if latest['vol_ma20'] > 0 else 0
    flow = "🔥 Tiền Vào Mạnh" if v_ratio >= 1.5 else ("⚡ Có Tín Hiệu" if v_ratio >= 1 else "💤 Tiền Yếu")

    gia_chiet_khau_sau = pct_vs_129 <= 5   # sát/dưới đường định giá 129
    bat_day = "🎯 BẮT ĐÁY (Vol {:.1f}x + giá chiết khấu 129)".format(v_ratio) \
        if (gia_chiet_khau_sau and v_ratio >= vol_spike_mult) else "-"

    # Cảnh báo tạo đỉnh: giá gần đỉnh nhưng thanh khoản kiệt dần
    near_high = close >= df['close'].rolling(20).max().iloc[-1] * 0.97
    canh_bao_dinh = near_high and v_ratio < 0.7

    # ------------------------------------------------------------------
    # 12. TÍN HIỆU MFI/RSI — CHỈ có giá trị khi đang Sideway (theo tài liệu)
    # ------------------------------------------------------------------
    rsi_v, mfi_v = latest['rsi14'], latest['mfi14']
    if xu_huong == "🟡 Sideway" and pd.notna(rsi_v) and pd.notna(mfi_v):
        if rsi_v <= 30 or mfi_v <= 30:
            tin_hieu_sideway = "🟢 Mua (vùng quá bán)"
        elif rsi_v >= 70 or mfi_v >= 70:
            tin_hieu_sideway = "🔴 Bán (vùng quá mua)"
        else:
            tin_hieu_sideway = "⏸️ Chờ (giữa biên độ)"
    else:
        tin_hieu_sideway = "— (đang có xu hướng, không dùng MFI/RSI)"

    # ------------------------------------------------------------------
    # 13. TRẠNG THÁI TỔNG (giữ tương thích với bộ lọc "Tất cả/Tích cực/Tiêu cực"
    #     ở sidebar hiện tại — sẽ nâng cấp radio 3 trạng thái ở bước sau)
    # ------------------------------------------------------------------
    if xu_huong == "🟢 Tăng":
        trang_thai = "🟢 Tích cực"
    elif xu_huong == "🔴 Giảm":
        trang_thai = "🔴 Tiêu cực"
    else:
        trang_thai = "🟡 Trung tính"

    return {
        "Mã CP": ticker,
        "Giá": close,
        "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Khối Lượng": int(latest['volume']),
        "KL TB 20 Phiên": int(latest['vol_ma20']),
        "Vol x TB20": round(v_ratio, 2),
        "Dòng Tiền": flow,
        "Xu Hướng": xu_huong,
        "Ichimoku_Cloud": cloud_status,
        "Kijun17": round(latest['kijun17'], 2),
        "Knife65": round(latest['knife65'], 2),
        "Knife129": round(latest['knife129'], 2),
        "Cách Knife129 (%)": round(pct_vs_129, 2),
        "Định Giá (129)": dinh_gia,
        "Hợp Bích (65≈129)": "✅" if hop_bich else "",
        "Cảnh Báo Mua Đuổi": "⚠️" if canh_bao_mua_duoi else "",
        "Cảnh Báo Tạo Đỉnh": "⚠️" if canh_bao_dinh else "",
        "Tín Hiệu Bắt Đáy": bat_day,
        "RSI14": round(rsi_v, 2) if pd.notna(rsi_v) else None,
        "MFI14": round(mfi_v, 2) if pd.notna(mfi_v) else None,
        "Tín Hiệu Sideway (MFI/RSI)": tin_hieu_sideway,
        "Trạng thái": trang_thai,
    }
