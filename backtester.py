import pandas as pd
import numpy as np
from vnstock import stock_historical_data
from datetime import datetime, timedelta

def get_5m_data(ticker, days_back=30):
    """Cào TRỰC TIẾP dữ liệu nến 5 phút từ API."""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    try:
        df_5m = stock_historical_data(symbol=ticker, 
                                      start_date=start_date, 
                                      end_date=end_date, 
                                      resolution="5", 
                                      type="stock")
        
        if df_5m is None or df_5m.empty:
            return None
            
        df_5m['time'] = pd.to_datetime(df_5m['time'])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_5m.columns:
                df_5m[col] = pd.to_numeric(df_5m[col], errors='coerce')
        
        df_5m = df_5m.sort_values('time').reset_index(drop=True)
        return df_5m
        
    except Exception as e:
        print(f"Lỗi cào dữ liệu 5 phút mã {ticker}: {e}")
        return None

def calculate_ichimoku_5m(df, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """Tính toán bộ Mây Ichimoku cho khung 5 Phút"""
    if df is None or len(df) < p_senkou_b:
        return None
        
    df['tenkan'] = (df['high'].rolling(window=p_tenkan).max() + df['low'].rolling(window=p_tenkan).min()) / 2
    df['kijun'] = (df['high'].rolling(window=p_kijun).max() + df['low'].rolling(window=p_kijun).min()) / 2
    
    senkou_a = (df['tenkan'] + df['kijun']) / 2
    df['senkou_a'] = senkou_a.shift(p_shift)
    
    period_high_s = df['high'].rolling(window=p_senkou_b).max()
    period_low_s = df['low'].rolling(window=p_senkou_b).min()
    df['senkou_b'] = ((period_high_s + period_low_s) / 2).shift(p_shift)
    
    df['cloud_top'] = df[['senkou_a', 'senkou_b']].max(axis=1)
    df['cloud_bottom'] = df[['senkou_a', 'senkou_b']].min(axis=1)
    
    return df.dropna()

def run_ichimoku_backtest(df, initial_capital=100000000):
    """
    Bộ não Backtest thông minh nâng cao:
    - Lưu lại Volume tại cây nến kích hoạt lệnh.
    - Tự động quét điều kiện Cắt lỗ (-5%) và Chốt lời (+7%) theo phân tích kỹ thuật Quant.
    """
    capital = initial_capital
    position = 0 
    buy_price = 0
    target_price = 0
    cutloss_price = 0
    trade_log = []
    
    # Tạo tín hiệu từ mây Kumo
    df['Buy_Signal'] = (df['close'] > df['cloud_top']) & (df['close'].shift(1) <= df['cloud_top'].shift(1))
    df['Sell_Signal'] = (df['close'] < df['cloud_bottom']) & (df['close'].shift(1) >= df['cloud_bottom'].shift(1))
    
    for index, row in df.iterrows():
        # 🟢 KIỂM TRA ĐIỀU KIỆN MUA
        if row['Buy_Signal'] and position == 0:
            position = capital // (row['close'] * 1000)
            buy_price = row['close']
            capital -= position * (buy_price * 1000)
            
            # Tính toán ngưỡng chốt lời / cắt lỗ động theo giá mua
            target_price = buy_price * 1.07   # Kỳ vọng lãi +7%
            cutloss_price = buy_price * 0.95  # Chấp nhận rủi ro tối đa -5%
            
            trade_log.append({
                'Thời gian': row['time'], 'Hành động': 'MUA', 'Giá khớp': buy_price, 
                'Vol nến 5P': row['volume'], 'Khối lượng nắm giữ': position,
                'Target (+7%)': round(target_price, 2), 'Cutloss (-5%)': round(cutloss_price, 2),
                'Lợi nhuận': '-', 'Ghi chú': 'Giá vượt mây Kumo', 'Vốn khả dụng': capital
            })
            continue

        # 🔴 KIỂM TRA ĐIỀU KIỆN BÁN (NẾU ĐANG CẦM CỔ PHIẾU)
        if position > 0:
            # Tình huống 1: Cây nến chạm ngưỡng Cắt lỗ (Ưu tiên kiểm tra trước để bảo vệ vốn)
            if row['low'] <= cutloss_price:
                capital += position * (cutloss_price * 1000)
                profit = (cutloss_price - buy_price) / buy_price * 100
                trade_log.append({
                    'Thời gian': row['time'], 'Hành động': '🔴 CẮT LỖ (Stoploss)', 'Giá khớp': cutloss_price, 
                    'Vol nến 5P': row['volume'], 'Khối lượng nắm giữ': 0,
                    'Target (+7%)': '-', 'Cutloss (-5%)': '-',
                    'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Chạm ngưỡng rủi ro -5%', 'Vốn khả dụng': capital
                })
                position = 0
                
            # Tình huống 2: Cây nến chạm ngưỡng Chốt lời mục tiêu
            elif row['high'] >= target_price:
                capital += position * (target_price * 1000)
                profit = (target_price - buy_price) / buy_price * 100
                trade_log.append({
                    'Thời gian': row['time'], 'Hành động': '🟢 CHỐT LỜI (Take Profit)', 'Giá khớp': target_price, 
                    'Vol nến 5P': row['volume'], 'Khối lượng nắm giữ': 0,
                    'Target (+7%)': '-', 'Cutloss (-5%)': '-',
                    'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Đạt kỳ vọng +7%', 'Vốn khả dụng': capital
                })
                position = 0
                
            # Tình huống 3: Chưa chạm ngưỡng trên/dưới nhưng chỉ báo mây Kumo bắt BÁN khẩn cấp
            elif row['Sell_Signal']:
                sell_price = row['close']
                capital += position * (sell_price * 1000)
                profit = (sell_price - buy_price) / buy_price * 100
                trade_log.append({
                    'Thời gian': row['time'], 'Hành động': 'BÁN (Chỉ báo)', 'Giá khớp': sell_price, 
                    'Vol nến 5P': row['volume'], 'Khối lượng nắm giữ': 0,
                    'Target (+7%)': '-', 'Cutloss (-5%)': '-',
                    'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Gãy dưới mây Kumo', 'Vốn khả dụng': capital
                })
                position = 0
                
    # Tất toán lệnh nếu ngày cuối kỳ khảo sát vẫn chưa bán hết hàng
    if position > 0:
        final_price = df.iloc[-1]['close']
        capital += position * (final_price * 1000)
        profit = (final_price - buy_price) / buy_price * 100
        trade_log.append({
            'Thời gian': df.iloc[-1]['time'], 'Hành động': 'BÁN (Chốt cuối kỳ)', 'Giá khớp': final_price, 
            'Vol nến 5P': df.iloc[-1]['volume'], 'Khối lượng nắm giữ': 0,
            'Target (+7%)': '-', 'Cutloss (-5%)': '-',
            'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Hết ngày khảo sát', 'Vốn khả dụng': capital
        })
        
    # Tạo bảng thống kê hiệu suất chung
    exit_orders = [t for t in trade_log if t['Hành động'] != 'MUA']
    total_trades = len(exit_orders)
    winning_trades = len([t for t in exit_orders if not t['Lợi nhuận'].startswith('-') and t['Lợi nhuận'] != '0.0%'])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    total_profit_pct = ((capital - initial_capital) / initial_capital) * 100
    
    stats = {
        "Vốn ban đầu": f"{initial_capital:,.0f} VNĐ",
        "Vốn cuối kỳ": f"{capital:,.0f} VNĐ",
        "Lợi nhuận ròng": f"{total_profit_pct:.2f}%",
        "Tổng số lệnh (Cặp Mua/Bán)": total_trades,
        "Tỷ lệ Thắng (Win Rate)": f"{win_rate:.2f}%"
    }
    
    return stats, pd.DataFrame(trade_log)
