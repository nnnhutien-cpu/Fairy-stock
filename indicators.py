import pandas as pd
import numpy as np

def calculate_technical_signals(df, ticker, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """Tính toán Ichimoku 5 đường và tự động đánh giá định giá theo Mây"""
    if df is None or len(df) < max(p_senkou_b, 60):
        return None
    
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # 1. TÍNH TOÁN RSI & MA
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean() 
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    # 2. HỆ SINH THÁI ICHIMOKU (5 ĐƯỜNG)
    df['Tenkan'] = (df['high'].rolling(window=p_tenkan).max() + df['low'].rolling(window=p_tenkan).min()) / 2
    df['Kijun'] = (df['high'].rolling(window=p_kijun).max() + df['low'].rolling(window=p_kijun).min()) / 2

    senkou_a = (df['Tenkan'] + df['Kijun']) / 2
    df['Senkou_A_Current'] = senkou_a.shift(p_shift)

    period_high_s = df['high'].rolling(window=p_senkou_b).max()
    period_low_s = df['low'].rolling(window=p_senkou_b).min()
    senkou_b = (period_high_s + period_low_s) / 2
    df['Senkou_B_Current'] = senkou_b.shift(p_shift)

    # Chikou Span
    df['Chikou'] = df['close']

    # 3. LẤY DỮ LIỆU PHIÊN CUỐI CÙNG
    latest = df.iloc[-1]
    price_val = latest['close']

    if price_val < 500: 
        gtgd_ty = (price_val * 1000 * latest['volume']) / 1_000_000_000
    else: 
        gtgd_ty = (price_val * latest['volume']) / 1_000_000_000

    if gtgd_ty < 20: 
        return None

    senkou_a_val = latest['Senkou_A_Current']
    senkou_b_val = latest['Senkou_B_Current']
    
    cloud_top = max(senkou_a_val, senkou_b_val)
    cloud_bottom = min(senkou_a_val, senkou_b_val)

    # THUẬT TOÁN ĐỊNH GIÁ THEO LOGIC MÂY ICHIMOKU CỦA BẠN
    if price_val > cloud_top:
        ichi_status = "☁️ Trên Mây"
        danh_gia_val = "📈 Định giá Cao"
    elif price_val < cloud_bottom:
        ichi_status = "🌧️ Dưới Mây"
        danh_gia_val = "📉 Định giá Thấp"
    else:
        ichi_status = "🌫️ Trong Mây"
        danh_gia_val = "⚖️ Hợp lý"

    if latest['close'] > latest['MA20'] and latest['RSI14'] > 50 and price_val > cloud_top:
        status_signal = "🟢 Tích cực"
    else:
        status_signal = "🔴 Tiêu cực"

    return {
        "Mã": ticker,
        "Giá": price_val,
        "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Khối Lượng": int(latest['volume']),
        "KL TB 20 Phiên": int(latest['Vol_MA20']) if pd.notna(latest['Vol_MA20']) else 0,
        "Đánh Giá": danh_gia_val, # Thêm cột đánh giá động
        "Tenkan": round(latest['Tenkan'], 2),
        "Kijun": round(latest['Kijun'], 2),
        "Senkou A": round(senkou_a_val, 2),
        "Senkou B": round(senkou_b_val, 2),
        "Chikou": round(latest['Chikou'], 2),
        "Ichimoku_Cloud": ichi_status,
        "Trạng thái": status_signal
    }
