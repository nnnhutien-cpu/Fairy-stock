import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import stock_historical_data


def _normalize(df):
    """Chuẩn hóa cột + kiểu dữ liệu cho khớp toàn hệ thống."""
    if df is None or df.empty:
        return None
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if 'date' in df.columns and 'time' not in df.columns:
        df.rename(columns={'date': 'time'}, inplace=True)
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
    # Ép giá/khối lượng về số — tránh lỗi rolling khi API trả chuỗi
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'time' in df.columns:
        df = df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
    return df


# 1. Cào dữ liệu Khung Ngày (1D)
def get_daily_data(ticker, years_back):
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=years_back * 365)).strftime('%Y-%m-%d')
    try:
        df = stock_historical_data(symbol=ticker, start_date=start_date,
                                   end_date=end_date, resolution="1D", type="stock")
        return _normalize(df)
    except Exception:
        return None


# 2. Tính Mây Ichimoku & Volume
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

    df['Vol_MA20'] = df['volume'].rolling(window=20).mean()

    df.dropna(subset=['Senkou_A', 'Senkou_B', 'Vol_MA20', 'Tenkan', 'Kijun'], inplace=True)
    df = df.reset_index(drop=True)
    return df if not df.empty else None


# 3. Vòng lặp Bot Giao Dịch (LOGIC PINE SCRIPT — GIỮ NGUYÊN)
def run_ichimoku_backtest_daily(df, initial_capital=100000000):
    capital = initial_capital
    position = 0
    buy_price = 0
    trade_log = []

    def fmt_date(d):
        return d.strftime('%Y-%m-%d') if isinstance(d, pd.Timestamp) else str(d)

    for i in range(1, len(df)):
        date = df['time'].iloc[i] if 'time' in df.columns else df.index[i]
        close = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        vol_ma20 = df['Vol_MA20'].iloc[i]

        tenkan = df['Tenkan'].iloc[i]
        kijun = df['Kijun'].iloc[i]
        senkou_a = df['Senkou_A'].iloc[i]
        senkou_b = df['Senkou_B'].iloc[i]

        cloudTop = max(senkou_a, senkou_b)
        cloudBot = min(senkou_a, senkou_b)

        isAboveCloud = close > cloudTop
        isVolOk = vol >= (vol_ma20 * 1.2)
        isMomentumUp = tenkan > kijun
        isNotDowntrend = close >= cloudBot

        # 🟢 MUA: isAboveCloud AND isVolOk AND isMomentumUp AND isNotDowntrend
        if position == 0:
            if isAboveCloud and isVolOk and isMomentumUp and isNotDowntrend:
                position = capital / close
                buy_price = close
                capital = 0
                trade_log.append({
                    "Ngày Mua": fmt_date(date),
                    "Giá Mua": buy_price,
                    "Khối Lượng": vol,
                    "Tín Hiệu": "Breakout Kép + Vol>120%",
                    "Ngày Bán": None,
                    "Giá Bán": None,
                    "Lợi Nhuận (%)": None,
                    "Lý Do Bán": None
                })

        # 🔴 BÁN: close < kijun OR close < cloudBot
        elif position > 0:
            sell_signal = ""
            if close < kijun:
                sell_signal = "BÁN (Gãy Kijun)"
            elif close < cloudBot:
                sell_signal = "BÁN (Gãy nền Mây)"

            if sell_signal:
                capital = position * close
                profit_realized = (close - buy_price) / buy_price
                trade_log[-1]["Ngày Bán"] = fmt_date(date)
                trade_log[-1]["Giá Bán"] = close
                trade_log[-1]["Lợi Nhuận (%)"] = round(profit_realized * 100, 2)
                trade_log[-1]["Lý Do Bán"] = sell_signal
                position = 0
                buy_price = 0

    # Tất toán lệnh cuối kỳ nếu còn cầm hàng
    if position > 0:
        close = df['close'].iloc[-1]
        date = df['time'].iloc[-1] if 'time' in df.columns else df.index[-1]
        capital = position * close
        profit_realized = (close - buy_price) / buy_price
        trade_log[-1]["Ngày Bán"] = fmt_date(date)
        trade_log[-1]["Giá Bán"] = close
        trade_log[-1]["Lợi Nhuận (%)"] = round(profit_realized * 100, 2)
        trade_log[-1]["Lý Do Bán"] = "Tất toán cuối kỳ"

    trade_df = pd.DataFrame(trade_log)

    net_profit_pct = ((capital - initial_capital) / initial_capital) * 100
    win_rate = 0
    total_trades = 0
    if not trade_df.empty:
        # Chỉ tính lệnh đã đóng (có lợi nhuận), tránh lỗi so sánh None
        closed = trade_df[trade_df["Lợi Nhuận (%)"].notna()]
        total_trades = len(closed)
        if total_trades > 0:
            win_trades = len(closed[closed["Lợi Nhuận (%)"] > 0])
            win_rate = (win_trades / total_trades) * 100

    stats = {
        "Vốn ban đầu": f"{initial_capital:,.0f} đ",
        "Vốn cuối kỳ": f"{capital:,.0f} đ",
        "Lợi nhuận ròng": f"{net_profit_pct:.2f}%",
        "Tỷ lệ Thắng (Win Rate)": f"{win_rate:.2f}%",
        "Số lệnh": total_trades
    }

    return stats, trade_df
