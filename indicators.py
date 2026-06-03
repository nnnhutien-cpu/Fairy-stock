import pandas as pd

def calculate_technical_signals(df, ticker, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    if df is None or len(df) < max(p_senkou_b, 60): return None
    
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # 1. Tính toán Kỹ thuật bằng Vector hóa (siêu nhanh)
    df['ma20'] = df['close'].rolling(20).mean()
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['rsi14'] = 100 - (100 / (1 + (df['close'].diff().clip(lower=0).rolling(14).mean() / -df['close'].diff().clip(upper=0).rolling(14).mean())))
    
    # 2. Ichimoku
    df['tenkan'] = (df['high'].rolling(p_tenkan).max() + df['low'].rolling(p_tenkan).min()) / 2
    df['kijun'] = (df['high'].rolling(p_kijun).max() + df['low'].rolling(p_kijun).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(p_shift)
    df['senkou_b'] = ((df['high'].rolling(p_senkou_b).max() + df['low'].rolling(p_senkou_b).min()) / 2).shift(p_shift)
    
    latest = df.iloc[-1]
    
    # 3. Bộ lọc thanh khoản (Logic gọn)
    gtgd_ty = (latest['close'] * (1000 if latest['close'] < 500 else 1) * latest['volume']) / 1_000_000_000
    if gtgd_ty < 20: return None

    # 4. Trạng thái & Định giá (Dùng List comprehension cho gọn)
    top, bot = max(latest['senkou_a'], latest['senkou_b']), min(latest['senkou_a'], latest['senkou_b'])
    status = "☁️ Trên Mây" if latest['close'] > top else ("🌧️ Dưới Mây" if latest['close'] < bot else "🌫️ Trong Mây")
    gia = "📈 Định giá Cao" if "Trên" in status else ("📉 Định giá Thấp" if "Dưới" in status else "⚖️ Hợp lý")
    
    v_ratio = latest['volume'] / latest['vol_ma20'] if latest['vol_ma20'] > 0 else 0
    flow = "🔥 Tiền Vào Mạnh" if v_ratio >= 1.5 else ("⚡ Có Tín Hiệu" if v_ratio >= 1 else "💤 Tiền Yếu")
    
    return {
        "Mã": ticker, "Giá": latest['close'], "GTGD (Tỷ)": round(gtgd_ty, 2),
        "Khối Lượng": int(latest['volume']), "KL TB 20 Phiên": int(latest['vol_ma20']),
        "Dòng Tiền": flow, "Đánh Giá": gia, "Tenkan": round(latest['tenkan'], 2),
        "Kijun": round(latest['kijun'], 2), "Senkou A": round(latest['senkou_a'], 2),
        "Senkou B": round(latest['senkou_b'], 2), "Chikou": round(latest['close'], 2),
        "Ichimoku_Cloud": status, "Trạng thái": "🟢 Tích cực" if latest['close'] > latest['ma20'] and latest['rsi14'] > 50 else "🔴 Tiêu cực"
    }
