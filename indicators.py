import pandas as pd
import numpy as np

def calculate_technical_signals(df, ticker):
    """Tính toán các chỉ báo kỹ thuật và trả về 1 dòng dữ liệu của ngày mới nhất"""
    if df is None or len(df) < 200:
        return None # Không đủ dữ liệu tính MA200
    
    # Tính các đường MA (Trung bình động)
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
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
    
    # Mây Kumo (Đơn giản hóa: So sánh giá hiện tại với mây)
    df['Ichimoku_Cloud_A'] = ((df['Ichimoku_Tenkan'] + df['Ichimoku_Kijun']) / 2).shift(26)
    df['Ichimoku_Cloud_B'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)
    
    # Tính Tín hiệu Volume (Ví dụ: Vol hôm nay > Trung bình 20 ngày)
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    df['Vol_Signal'] = np.where(df['volume'] > df['Vol_MA20'] * 1.2, "Bùng nổ", "Bình thường")
    
    # Tính Tín hiệu Mua/Bán (Signal)
    # Ví dụ đơn giản: Giá cắt lên MA20 và RSI > 50 là Mua
    df['Signal'] = np.where((df['close'] > df['MA20']) & (df['RSI14'] > 50), "🟢 Tích cực", "🔴 Yếu")
    
    # Xác định trạng thái Mây Ichimoku
    df['Ichimoku_Cloud'] = np.where(
        (df['close'] > df['Ichimoku_Cloud_A']) & (df['close'] > df['Ichimoku_Cloud_B']), "Giá trên Mây (Tốt)",
        np.where((df['close'] < df['Ichimoku_Cloud_A']) & (df['close'] < df['Ichimoku_Cloud_B']), "Giá dưới Mây (Xấu)", "Giá trong Mây")
    )

    # Lấy dòng dữ liệu mới nhất (hôm nay)
    latest = df.iloc[-1]
    
    return {
        "Date": latest['time'],
        "Ticker": ticker,
        "Close": latest['close'],
        "MA20": round(latest['MA20'], 2),
        "MA50": round(latest['MA50'], 2),
        "MA200": round(latest['MA200'], 2),
        "RSI14": round(latest['RSI14'], 2),
        "Ichimoku_Tenkan": round(latest['Ichimoku_Tenkan'], 2),
        "Ichimoku_Kijun": round(latest['Ichimoku_Kijun'], 2),
        "Ichimoku_Cloud": latest['Ichimoku_Cloud'],
        "Vol_Signal": latest['Vol_Signal'],
        "Signal": latest['Signal']
    }
