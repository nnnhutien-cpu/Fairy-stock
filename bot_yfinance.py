import gspread
from google.oauth2.service_account import Credentials
from vnstock import Vnstock
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# HÀM TÍNH TOÁN CHỈ SỐ KỸ THUẬT (THAY THẾ pandas_ta)
# ==========================================
def calc_rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=length).mean()
    loss = (-delta.clip(upper=0)).rolling(window=length).mean()
    rs = gain / loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))

def calc_sma(series, length):
    return series.rolling(window=length).mean()

def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({
        'MACD_12_26_9': macd_line,
        'MACDs_12_26_9': signal_line,
        'MACDh_12_26_9': histogram
    })

# ==========================================
# 1. CẤU HÌNH KẾT NỐI GOOGLE SHEETS
# ==========================================
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file('credentials.json', scopes=scopes)
gc = gspread.authorize(credentials)

# ĐIỀN ID FILE GOOGLE SHEETS CỦA BẠN VÀO ĐÂY
SPREADSHEET_ID = 'ĐIỀN_ID_FILE_CỦA_BẠN_VÀO_ĐÂY'
sh = gc.open_by_key(SPREADSHEET_ID)

TICKERS = ['SSI', 'VND', 'HPG', 'FPT', 'VCB']

end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

df_prices_all = pd.DataFrame()
df_tech_all = pd.DataFrame()
df_foreign_all = pd.DataFrame()
df_ratios_all = pd.DataFrame()
alerts_list = []

print("🚀 Đang khởi động cỗ máy cào dữ liệu 6 Sheets...")

# ==========================================
# 2. VÒNG LẶP XỬ LÝ TỪNG MÃ CỔ PHIẾU
# ==========================================
for ticker in TICKERS:
    try:
        print(f"Đang xử lý: {ticker}...")
        stock = Vnstock().stock(symbol=ticker, source='VCI')

        # --- SHEET 2: STOCK PRICES ---
        df_hist = stock.quote.history(start=start_date, end=end_date)
        if df_hist.empty:
            continue

        df_hist['Ticker'] = ticker
        latest_price = df_hist.iloc[-1:].copy()
        df_prices_all = pd.concat([df_prices_all, latest_price])

        # --- SHEET 3: TECHNICAL SIGNALS ---
        df_hist['RSI'] = calc_rsi(df_hist['close'], length=14)
        df_hist['MA20'] = calc_sma(df_hist['close'], length=20)
        macd_df = calc_macd(df_hist['close'])
        df_hist = pd.concat([df_hist, macd_df], axis=1)

        latest_tech = df_hist.iloc[-1:].copy()
        latest_tech['Ticker'] = ticker
        df_tech_all = pd.concat([df_tech_all, latest_tech])

        # --- SHEET 6: MARKET ALERTS ---
        df_hist['Vol_MA20'] = calc_sma(df_hist['volume'], length=20)
        current_vol = df_hist['volume'].iloc[-1]
        avg_vol = df_hist['Vol_MA20'].iloc[-1]

        if pd.notna(avg_vol) and avg_vol > 0 and current_vol > (avg_vol * 1.5):
            alerts_list.append({
                'Date': end_date,
                'Ticker': ticker,
                'Alert_Type': 'Volume Breakout',
                'Message': f"Khối lượng đột biến: {current_vol} (Gấp {round(current_vol/avg_vol, 1)} lần TB 20 phiên)"
            })

        # --- SHEET 4: FOREIGN TRADE ---
        try:
            df_foreign = stock.finance.foreign_flow()
            if not df_foreign.empty:
                df_foreign['Ticker'] = ticker
                df_foreign_all = pd.concat([df_foreign_all, df_foreign.head(1)])
        except Exception:
            pass

        # --- SHEET 5: FINANCIAL RATIOS ---
        try:
            df_ratio = stock.finance.ratio()
            if not df_ratio.empty:
                df_ratio['Ticker'] = ticker
                df_ratios_all = pd.concat([df_ratios_all, df_ratio.head(1)])
        except Exception:
            pass

    except Exception as e:
        print(f"Lỗi ở mã {ticker}: {e}")

# --- SHEET 1: MARKET OVERVIEW ---
try:
    vnindex = Vnstock().stock(symbol='VNINDEX', source='VCI').quote.history(start=start_date, end=end_date)
    df_overview = vnindex.iloc[-5:].copy()
    df_overview['Index'] = 'VNINDEX'
except Exception:
    df_overview = pd.DataFrame([{'Index': 'VNINDEX', 'Status': 'Data not available'}])

df_alerts_all = (
    pd.DataFrame(alerts_list)
    if alerts_list
    else pd.DataFrame([{'Date': end_date, 'Message': 'Không có tín hiệu đột biến nào'}])
)

# ==========================================
# 3. HÀM ĐẨY DỮ LIỆU LÊN GOOGLE SHEETS
# ==========================================
def push_to_sheet(worksheet_name, df):
    try:
        ws = sh.worksheet(worksheet_name)
        if df.empty:
            return

        for col in df.select_dtypes(
            include=['datetime64[ns, UTC]', 'datetime64[ns]', 'datetime']
        ).columns:
            df[col] = df[col].dt.strftime('%Y-%m-%d')

        df = df.fillna('')
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"✅ Đã cập nhật thành công tab: {worksheet_name}")
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật tab {worksheet_name}: {e}")

push_to_sheet("Market_Overview",   df_overview)
push_to_sheet("Stock_Prices",      df_prices_all)
push_to_sheet("Technical_Signals", df_tech_all)
push_to_sheet("Foreign_Trade",     df_foreign_all)
push_to_sheet("Financial_Ratios",  df_ratios_all)
push_to_sheet("Market_Alerts",     df_alerts_all)

print("🎉 XONG! TOÀN BỘ HỆ THỐNG 6 SHEET ĐÃ ĐƯỢC CẬP NHẬT TỰ ĐỘNG.")
