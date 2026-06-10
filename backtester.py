import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import stock_historical_data

# 1. Hàm cào dữ liệu Khung Ngày (1D)
def get_daily_data(ticker, years_back):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=years_back * 365)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution="1D", type="stock")
        if df is not None and not df.empty:
            df.columns = [str(c).lower().strip() for c in df.columns]
            return df
    except:
        pass
    return None

# 2. Hàm tính toán Đám Mây & Trung Bình Khối Lượng (MA20)
def calculate_ichimoku_daily(df, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    if df is None or len(df) < p_senkou_b + p_shift:
        return None
    
    df = df.copy()
    
    df['Tenkan'] = (df['high'].rolling(window=p_tenkan).max() + df['low'].rolling(window=p_tenkan).min()) / 2
    df['Kijun'] = (df['high'].rolling(window=p_kijun).max() + df['low'].rolling(window=p_kijun).min()) / 2
    
    senkou_a_raw = (df['Tenkan'] + df['Kijun']) / 2
    df['Senkou_A'] = senkou_a_raw.shift(p_shift)
    
    senkou_b_raw = (df['high'].rolling(window=p_senkou_b).max() + df['low'].rolling(window=p_senkou_b).min()) / 2
    df['Senkou_B'] = senkou_b_raw.shift(p_shift)
    
    # Tính Trung bình Khối lượng 20 phiên (Volume MA20)
    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
    
    df.dropna(subset=['Senkou_A', 'Senkou_B', 'Vol_MA20'], inplace=True)
    return df

# 3. Vòng lặp Bot Giao Dịch - Phiên bản "Bộ Lọc Tinh Chỉnh - Win Rate Cao"
def run_ichimoku_backtest_daily(df, initial_capital=100000000, stop_loss_pct=-0.07):
    capital = initial_capital
    position = 0
    buy_price = 0
    trade_log = []
    
    for i in range(1, len(df)):
        date = df['time'].iloc[i] if 'time' in df.columns else df.index[i]
        close = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        vol_ma20 = df['Vol_MA20'].iloc[i]
        
        # Xác định các đường biên Ichimoku
        senkou_a = df['Senkou_A'].iloc[i]
        senkou_b = df['Senkou_B'].iloc[i]
        tenkan = df['Tenkan'].iloc[i] # Lấy thêm Tenkan để bảo vệ lãi
        kijun = df['Kijun'].iloc[i]  
        
        top_kumo = max(senkou_a, senkou_b)
        bot_kumo = min(senkou_a, senkou_b)
        
        # ==========================================
        # 🟢 LOGIC MUA (BUY): Khắt khe hơn để lọc nhiễu (Bull Trap)
        # ==========================================
        if position == 0:
            # 1. Giá trên mây (Uptrend dài)
            # 2. Tenkan > Kijun (Uptrend ngắn đã xác nhận)
            # 3. Vol > 1.2 lần Vol_MA20 (Dòng tiền lớn thực sự vào)
            if (close > top_kumo) and (tenkan > kijun) and (vol > (vol_ma20 * 1.2)):
                position = capital / close
                buy_price = close
                capital = 0
                trade_log.append({
                    "Ngày Mua": date.strftime('%Y-%m-%d') if isinstance(date, pd.Timestamp) else date, 
                    "Giá Mua": buy_price, 
                    "Khối Lượng": vol, 
                    "Tín Hiệu": "Breakout Kép + Vol Siêu Lớn",
                    "Ngày Bán": None,
                    "Giá Bán": None,
                    "Lợi Nhuận (%)": None,
                    "Lý Do Bán": None
                })
                
        # ==========================================
        # 🔴 LOGIC BÁN (SELL): Tối ưu điểm ra để khóa lãi
        # ==========================================
        elif position > 0:
            profit_pct = (close - buy_price) / buy_price
            sell_signal = ""
            
            # 1. Cắt lỗ cứng bảo vệ vốn (-7%)
            if profit_pct <= stop_loss_pct:
                sell_signal = f"Cắt Lỗ ({stop_loss
