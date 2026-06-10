import pandas as pd
import numpy as np
from vnstock import stock_historical_data
from datetime import datetime, timedelta

def get_daily_data(ticker, years_back=5):
    """Cào trực tiếp dữ liệu nến Ngày (1D) lên tới 5-10 năm từ API."""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=years_back * 365)).strftime('%Y-%m-%d')
    
    try:
        df_daily = stock_historical_data(symbol=ticker, 
                                      start_date=start_date, 
                                      end_date=end_date, 
                                      resolution="1D", 
                                      type="stock")
        
        if df_daily is None or df_daily.empty:
            return None
            
        df_daily['time'] = pd.to_datetime(df_daily['time'])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_daily.columns:
                df_daily[col] = pd.to_numeric(df_daily[col], errors='coerce')
        
        df_daily = df_daily.sort_values('time').reset_index(drop=True)
        return df_daily
        
    except Exception as e:
        print(f"Lỗi cào dữ liệu Daily mã {ticker}: {e}")
        return None

def calculate_ichimoku_daily(df, p_tenkan=9, p_kijun=26, p_senkou_b=52, p_shift=26):
    """Tính toán bộ Mây Ichimoku cho khung Ngày"""
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

def run_ichimoku_backtest_daily(df, initial_capital=100000000):
    """
    Bộ não Backtest Daily Tối Thượng:
    - Quét râu nến (High/Low) để chốt lời/cắt lỗ trong phiên.
    - Biên độ chuẩn Swing Trade: Cắt lỗ -7%, Chốt lời +15%.
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
        trade_date = row['time'].strftime('%Y-%m-%d')
        
        # 🟢 KIỂM TRA ĐIỀU KIỆN MUA
        if row['Buy_Signal'] and position == 0:
            position = capital // (row['close'] * 1000)
            buy_price = row['close']
            capital -= position * (buy_price * 1000)
            
            # Tính toán ngưỡng chốt lời / cắt lỗ động cho Khung Ngày
            target_price = buy_price * 1.15   # Kỳ vọng lãi +15%
            cutloss_price = buy_price * 0.93  # Chấp nhận rủi ro tối đa -7%
            
            trade_log.append({
                'Ngày giao dịch': trade_date, 'Hành động': 'MUA', 'Giá khớp': buy_price, 
                'Volume 1D': row['volume'], 'Số lượng': position,
                'Target (+15%)': round(target_price, 2), 'Cutloss (-7%)': round(cutloss_price, 2),
                'Lợi nhuận': '-', 'Ghi chú': 'Giá vượt mây Kumo', 'Vốn khả dụng': capital
            })
            continue

        # 🔴 KIỂM TRA ĐIỀU KIỆN BÁN
        if position > 0:
            # Tình huống 1: Râu nến đâm thủng ngưỡng Cắt lỗ (Ưu tiên số 1)
            if row['low'] <= cutloss_price:
                capital += position * (cutloss_price * 1000)
                profit = (cutloss_price - buy_price) / buy_price * 100
                trade_log.append({
                    'Ngày giao dịch': trade_date, 'Hành động': '🔴 CẮT LỖ', 'Giá khớp': cutloss_price, 
                    'Volume 1D': row['volume'], 'Số lượng': 0,
                    'Target (+15%)': '-', 'Cutloss (-7%)': '-',
                    'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Chạm rủi ro -7%', 'Vốn khả dụng': capital
                })
                position = 0
                
            # Tình huống 2: Kéo vọt lên chạm ngưỡng Chốt lời
            elif row['high'] >= target_price:
                capital += position * (target_price * 1000)
                profit = (target_price - buy_price) / buy_price * 100
                trade_log.append({
                    'Ngày giao dịch': trade_date, 'Hành động': '🟢 CHỐT LỜI', 'Giá khớp': target_price, 
                    'Volume 1D': row['volume'], 'Số lượng': 0,
                    'Target (+15%)': '-', 'Cutloss (-7%)': '-',
                    'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Đạt kỳ vọng +15%', 'Vốn khả dụng': capital
                })
                position = 0
                
            # Tình huống 3: Mất xu hướng (Gãy mây Kumo) trước khi chạm Target/Cutloss
            elif row['Sell_Signal']:
                sell_price = row['close']
                capital += position * (sell_price * 1000)
                profit = (sell_price - buy_price) / buy_price * 100
                trade_log.append({
                    'Ngày giao dịch': trade_date, 'Hành động': 'BÁN (Gãy mây)', 'Giá khớp': sell_price, 
                    'Volume 1D': row['volume'], 'Số lượng': 0,
                    'Target (+15%)': '-', 'Cutloss (-7%)': '-',
                    'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Mất xu hướng Daily', 'Vốn khả dụng': capital
                })
                position = 0
                
    # Tất toán lệnh cuối kỳ
    if position > 0:
        final_price = df.iloc[-1]['close']
        capital += position * (final_price * 1000)
        profit = (final_price - buy_price) / buy_price * 100
        trade_log.append({
            'Ngày giao dịch': df.iloc[-1]['time'].strftime('%Y-%m-%d'), 'Hành động': 'BÁN (Chốt cuối kỳ)', 'Giá khớp': final_price, 
            'Volume 1D': df.iloc[-1]['volume'], 'Số lượng': 0,
            'Target (+15%)': '-', 'Cutloss (-7%)': '-',
            'Lợi nhuận': f"{round(profit, 2)}%", 'Ghi chú': 'Hết 5 năm khảo sát', 'Vốn khả dụng': capital
        })
        
    # Thống kê hiệu suất
    exit_orders = [t for t in trade_log if t['Hành động'] != 'MUA']
    total_trades = len(exit_orders)
    winning_trades = len([t for t in exit_orders if not t['Lợi nhuận'].startswith('-') and t['Lợi nhuận'] != '0.0%'])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    total_profit_pct = ((capital - initial_capital) / initial_capital) * 100
    
    stats = {
        "Vốn ban đầu": f"{initial_capital:,.0f} VNĐ",
        "Vốn cuối kỳ": f"{capital:,.0f} VNĐ",
        "Lợi nhuận ròng": f"{total_profit_pct:.2f}%",
        "Tổng số lệnh (Cặp M/B)": total_trades,
        "Tỷ lệ Thắng (Win Rate)": f"{win_rate:.2f}%"
    }
    
    return stats, pd.DataFrame(trade_log)
