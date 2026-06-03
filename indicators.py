import pandas as pd
import numpy as np

def calculate_technical_signals(df, ticker):
    """Tính toán chỉ báo kỹ thuật cho cả mã Tích cực và Tiêu cực"""
    if df is None or len(df) < 200:
        return None
    
    # Tính các đường chỉ báo cơ sở
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA200'] = df['close'].rolling(window=200).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    latest = df.iloc[-1]
    
    # Tính toán giá trị giao dịch (Đổi ra đơn vị Tỷ VNĐ)
    price_val = latest['close']
    if price_val < 500: 
        gtgd_ty = (price_val * 1000 * latest['volume']) / 1_000_000_000
    else: 
        gtgd_ty = (price_val * latest['volume']) / 1_000_000_000

    # TIÊU CHÍ THANH KHOẢN: Bắt buộc một phiên phải giao dịch trên 20 Tỷ VNĐ
    if gtgd_ty < 20:
        return None

    # THUẬT TOÁN PHÂN LOẠI TÍN HIỆU THEO YÊU CẦU CỦA BẠN
    if latest['close'] > latest['MA20'] and latest['RSI14'] > 50:
        status_signal = "🟢 Tích cực"
    else:
        status_signal = "🔴 Tiêu cực"

    return {
        "Mã": ticker,
        "Giá": price_val,
        "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Volume Hiện Tại": int(latest['volume']),
        "Volume TB 20 Phiên": int(latest['Vol_MA20']),
        "MA20": round(latest['MA20'], 2),
        "MA200": round(latest['MA200'], 2),
        "RSI14": round(latest['RSI14'], 2),
        "Trạng thái": status_signal
    }
