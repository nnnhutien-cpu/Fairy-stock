import pandas as pd
import numpy as np

def calculate_technical_signals(df, ticker):
    """Tính toán các chỉ báo kỹ thuật và lọc theo thanh khoản"""
    if df is None or len(df) < 200:
        return None # Không đủ dữ liệu tính MA200
    
    # Tính các đường MA (ĐÃ BỎ ĐƯỜNG MA50 THEO YÊU CẦU)
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA200'] = df['close'].rolling(window=200).mean()
    
    # Tính RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    # Tính Ichimoku
    high_9 = df['high'].rolling(window=9).max()
    low_9 = df['low'].rolling(window=9).min()
    df['Ichimoku_Tenkan'] = (high_9 + low_9) / 2
    
    high_26 = df['high'].rolling(window=26).max()
    low_26 = df['low'].rolling(window=26).min()
    df['Ichimoku_Kijun'] = (high_26 + low_26) / 2
    
    # Mây Kumo
    df['Ichimoku_Cloud_A'] = ((df['Ichimoku_Tenkan'] + df['Ichimoku_Kijun']) / 2).shift(26)
    df['Ichimoku_Cloud_B'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)
    
    # Tính Khối lượng trung bình 20 phiên
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    df['Vol_Signal'] = np.where(df['volume'] > df['Vol_MA20'] * 1.2, "Bùng nổ", "Bình thường")
    
    # Tính Tín hiệu Mua/Bán (Giá > MA20 và RSI > 50)
    df['Signal'] = np.where((df['close'] > df['MA20']) & (df['RSI14'] > 50), "🟢 Tích cực", "🔴 Yếu")
    
    # Xác định trạng thái Mây Ichimoku
    df['Ichimoku_Cloud'] = np.where(
        (df['close'] > df['Ichimoku_Cloud_A']) & (df['close'] > df['Ichimoku_Cloud_B']), "Giá trên Mây (Tốt)",
        np.where((df['close'] < df['Ichimoku_Cloud_A']) & (df['close'] < df['Ichimoku_Cloud_B']), "Giá dưới Mây (Xấu)", "Giá trong Mây")
    )

    latest = df.iloc[-1]
    
    # Tính Giá trị giao dịch (Tỷ VNĐ)
    price_val = latest['close']
    if price_val < 500: 
        gtgd_ty = (price_val * 1000 * latest['volume']) / 1_000_000_000
    else: 
        gtgd_ty = (price_val * latest['volume']) / 1_000_000_000

    # BỘ LỌC CHỈ TIÊU: GTGD > 20 Tỷ và Tín hiệu phải Tích cực
    if gtgd_ty < 20 or latest['Signal'] != "🟢 Tích cực":
        return None

    # Trả về kết quả hiển thị (Đã thêm 2 cột Volume dạng số nguyên và bỏ MA50)
    return {
        "Mã": ticker,
        "Giá": price_val,
        "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Volume Hiện Tại": int(latest['volume']),
        "Volume TB 20 Phiên": int(latest['Vol_MA20']),
        "MA20": round(latest['MA20'], 2),
        "MA200": round(latest['MA200'], 2),
        "RSI14": round(latest['RSI14'], 2),
        "Mây Ichimoku": latest['Ichimoku_Cloud'],
        "Tín hiệu": latest['Signal']
    }
