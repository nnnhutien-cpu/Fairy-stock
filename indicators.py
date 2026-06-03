import pandas as pd
import numpy as np

def calculate_technical_signals(df, ticker):
    """Tính toán chỉ báo kỹ thuật bao gồm Ichimoku Cloud hoàn chỉnh"""
    # Cần ít nhất 60 phiên để Mây Ichimoku hình thành chuẩn xác
    if df is None or len(df) < 60:
        return None
    
    # Chuẩn hóa tên cột để chống lỗi
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # 1. TÍNH TOÁN RSI & MA
    df['MA20'] = df['close'].rolling(window=20).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    # 2. TÍNH TOÁN HỆ SINH THÁI ICHIMOKU
    # Tenkan-sen (Đường chuyển đổi - 9 phiên)
    period9_high = df['high'].rolling(window=9).max()
    period9_low = df['low'].rolling(window=9).min()
    df['Tenkan'] = (period9_high + period9_low) / 2

    # Kijun-sen (Đường cơ sở - 26 phiên)
    period26_high = df['high'].rolling(window=26).max()
    period26_low = df['low'].rolling(window=26).min()
    df['Kijun'] = (period26_high + period26_low) / 2

    # Senkou Span A (Đẩy về phía trước 26 phiên - Tương lai)
    # Nhưng để lấy giá trị mây của ngày HÔM NAY, ta lùi lại 26 phiên
    senkou_a = (df['Tenkan'] + df['Kijun']) / 2
    df['Senkou_A_Current'] = senkou_a.shift(26)

    # Senkou Span B (52 phiên, lùi 26)
    period52_high = df['high'].rolling(window=52).max()
    period52_low = df['low'].rolling(window=52).min()
    senkou_b = (period52_high + period52_low) / 2
    df['Senkou_B_Current'] = senkou_b.shift(26)

    # 3. LẤY DỮ LIỆU PHIÊN CUỐI CÙNG
    latest = df.iloc[-1]
    price_val = latest['close']

    # Thanh khoản (Tỷ VNĐ)
    if price_val < 500: 
        gtgd_ty = (price_val * 1000 * latest['volume']) / 1_000_000_000
    else: 
        gtgd_ty = (price_val * latest['volume']) / 1_000_000_000

    if gtgd_ty < 20: # Lọc bỏ cổ phiếu rác dưới 20 tỷ
        return None

    # Lấy thông số Mây Kumo hiện tại
    senkou_a_val = latest['Senkou_A_Current']
    senkou_b_val = latest['Senkou_B_Current']
    
    # Xét vị trí Giá so với Mây Ichimoku
    cloud_top = max(senkou_a_val, senkou_b_val)
    cloud_bottom = min(senkou_a_val, senkou_b_val)

    if price_val > cloud_top:
        ichi_status = "☁️ Trên Mây"
    elif price_val < cloud_bottom:
        ichi_status = "🌧️ Dưới Mây"
    else:
        ichi_status = "🌫️ Trong Mây"

    # ĐỊNH NGHĨA SIÊU CỔ PHIẾU TÍCH CỰC: Giá > MA20 & RSI > 50 & Đã Vượt Mây
    if latest['close'] > latest['MA20'] and latest['RSI14'] > 50 and price_val > cloud_top:
        status_signal = "🟢 Tích cực"
    else:
        status_signal = "🔴 Tiêu cực"

    return {
        "Mã": ticker,
        "Giá": price_val,
        "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Khối Lượng": int(latest['volume']),
        "Ichimoku_Tenkan": round(latest['Tenkan'], 2),
        "Ichimoku_Kijun": round(latest['Kijun'], 2),
        "Senkou A": round(senkou_a_val, 2),
        "Senkou B": round(senkou_b_val, 2),
        "Ichimoku_Cloud": ichi_status,
        "Trạng thái": status_signal
    }
