import pandas as pd
import numpy as np

def calculate_technical_signals(df, ticker, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """Tính toán Ichimoku 5 đường, Đánh giá mây và Đo dòng tiền thông minh"""
    if df is None or len(df) < max(p_senkou_b, 60):
        return None
    
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # 1. TÍNH TOÁN RSI & MA GIÁ & MA KHỐI LƯỢNG
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['vol_ma20'] = df['volume'].rolling(window=20).mean() 
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi14'] = 100 - (100 / (1 + rs))
    
    # 2. HỆ SINH THÁI ICHIMOKU (5 ĐƯỜNG)
    df['tenkan'] = (df['high'].rolling(window=p_tenkan).max() + df['low'].rolling(window=p_tenkan).min()) / 2
    df['kijun'] = (df['high'].rolling(window=p_kijun).max() + df['low'].rolling(window=p_kijun).min()) / 2

    senkou_a = (df['tenkan'] + df['kijun']) / 2
    df['senkou_a_current'] = senkou_a.shift(p_shift)

    period_high_s = df['high'].rolling(window=p_senkou_b).max()
    period_low_s = df['low'].rolling(window=p_senkou_b).min()
    df['senkou_b_current'] = period_high_s.shift(p_shift) # Chuẩn hóa theo trục dịch chuyển

    # 3. LẤY DỮ LIỆU PHIÊN CUỐI CÙNG
    latest = df.iloc[-1]
    price_val = latest['close']
    vol_current = latest['volume']
    vol_ma20_val = latest['vol_ma20']

    # Tính Giá trị giao dịch (GTGD) quy đổi ra Tỷ VNĐ
    if price_val < 500: 
        gtgd_ty = (price_val * 1000 * vol_current) / 1_000_000_000
    else: 
        gtgd_ty = (price_val * vol_current) / 1_000_000_000

    if gtgd_ty < 20: # Bộ lọc cơ sở loại bỏ mã thanh khoản yếu dưới 20 tỷ
        return None

    senkou_a_val = latest['senkou_a_current']
    senkou_b_val = latest['senkou_b_current']
    
    cloud_top = max(senkou_a_val, senkou_b_val)
    cloud_bottom = min(senkou_a_val, senkou_b_val)

    # THUẬT TOÁN ĐỊNH GIÁ THEO MÂY ICHIMOKU
    if price_val > cloud_top:
        ichi_status = "☁️ Trên Mây"
        danh_gia_val = "📈 Định giá Cao"
    elif price_val < cloud_bottom:
        ichi_status = "🌧️ Dưới Mây"
        danh_gia_val = "📉 Định giá Thấp"
    else:
        ichi_status = "🌫️ Trong Mây"
        danh_gia_val = "⚖️ Hợp lý"

    # [MỚI] THUẬT TOÁN ĐO DÒNG TIỀN THỰC CHIẾN
    if pd.notna(vol_ma20_val) and vol_ma20_val > 0:
        vol_ratio = vol_current / vol_ma20_val
        if vol_ratio >= 1.5:
            dong_tien_val = "🔥 Tiền Vào Mạnh"
        elif vol_ratio >= 1.0:
            dong_tien_val = "⚡ Có Tín Hiệu"
        else:
            dong_tien_val = "💤 Tiền Yếu"
    else:
        dong_tien_val = "⚪ Không rõ"

    # Định nghĩa trạng thái Tích cực/Tiêu cực chung
    if latest['close'] > latest['ma20'] and latest['rsi14'] > 50 and price_val > cloud_top:
        status_signal = "🟢 Tích cực"
    else:
        status_signal = "🔴 Tiêu cực"

    return {
        "Mã": ticker,
        "Giá": price_val,
        "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Khối Lượng": int(vol_current),
        "KL TB 20 Phiên": int(vol_ma20_val) if pd.notna(vol_ma20_val) else 0,
        "Dòng Tiền": dong_tien_val, # Cột mới đo dòng tiền nóng
        "Đánh Giá": danh_gia_val,
        "Tenkan": round(latest['tenkan'], 2),
        "Kijun": round(latest['kijun'], 2),
        "Senkou A": round(senkou_a_val, 2),
        "Senkou B": round(senkou_b_val, 2),
        "Chikou": round(price_val, 2),
        "Ichimoku_Cloud": ichi_status,
        "Trạng thái": status_signal
    }
