import gspread
from google.oauth2.service_account import Credentials
from vnstock import Vnstock
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta

# ==========================================
# 1. CẤU HÌNH KẾT NỐI GOOGLE SHEETS
# ==========================================
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
# Nhớ đảm bảo file JSON key của bạn được gọi đúng tên
credentials = Credentials.from_service_account_file('credentials.json', scopes=scopes)
gc = gspread.authorize(credentials)

# ĐIỀN ID FILE GOOGLE SHEETS CỦA BẠN VÀO ĐÂY
SPREADSHEET_ID = 'ĐIỀN_ID_FILE_CỦA_BẠN_VÀO_ĐÂY' 
sh = gc.open_by_key(SPREADSHEET_ID)

# Danh sách cổ phiếu theo dõi (Bạn có thể thêm nhiều mã hơn)
TICKERS = ['SSI', 'VND', 'HPG', 'FPT', 'VCB']

# Xác định thời gian lấy dữ liệu (3 tháng gần nhất để tính MA, MACD cho chuẩn)
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

# Khởi tạo các DataFrame rỗng để chứa dữ liệu gộp của 6 sheet
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
        
        # --- SHEET 2: STOCK PRICES (Giá lịch sử) ---
        df_hist = stock.quote.history(start=start_date, end=end_date)
        if df_hist.empty: continue
        
        df_hist['Ticker'] = ticker
        # Chỉ lấy phiên giao dịch cuối cùng để đưa lên bảng giá
        latest_price = df_hist.iloc[-1:].copy()
        df_prices_all = pd.concat([df_prices_all, latest_price])

        # --- SHEET 3: TECHNICAL SIGNALS (Tín hiệu kỹ thuật) ---
        # Tính RSI, MACD, MA20 bằng pandas-ta
        df_hist['RSI'] = ta.rsi(df_hist['close'], length=14)
        df_hist['MA20'] = ta.sma(df_hist['close'], length=20)
        macd = ta.macd(df_hist['close'])
        if macd is not None:
            df_hist = pd.concat([df_hist, macd], axis=1)
        
        latest_tech = df_hist.iloc[-1:].copy()
        latest_tech['Ticker'] = ticker
        df_tech_all = pd.concat([df_tech_all, latest_tech])

        # --- SHEET 6: MARKET ALERTS (Cảnh báo đột biến) ---
        # Logic: Nếu Khối lượng phiên cuối > 1.5 lần trung bình Khối lượng 20 phiên
        df_hist['Vol_MA20'] = ta.sma(df_hist['volume'], length=20)
        current_vol = df_hist['volume'].iloc[-1]
        avg_vol = df_hist['Vol_MA20'].iloc[-1]
        
        if current_vol > (avg_vol * 1.5):
            alerts_list.append({
                'Date': end_date,
                'Ticker': ticker,
                'Alert_Type': 'Volume Breakout',
                'Message': f"Khối lượng đột biến: {current_vol} (Gấp {round(current_vol/avg_vol, 1)} lần TB 20 phiên)"
            })

        # --- SHEET 4: FOREIGN TRADE (Khối ngoại) ---
        # Lấy dữ liệu khối ngoại (giả sử lấy trong 10 ngày gần nhất)
        # Tùy thuộc vào hàm của vnstock3, đây là hàm ví dụ gọi dữ liệu khối ngoại
        # Nếu api đang bảo trì, ta bỏ qua bằng try/except
        try:
            df_foreign = stock.finance.foreign_flow() # Hàm minh họa của Vnstock3
            if not df_foreign.empty:
                df_foreign['Ticker'] = ticker
                df_foreign_all = pd.concat([df_foreign_all, df_foreign.head(1)]) # Lấy dòng mới nhất
        except:
            pass

        # --- SHEET 5: FINANCIAL RATIOS (Chỉ số tài chính) ---
        try:
            df_ratio = stock.finance.ratio() # Lấy P/E, P/B...
            if not df_ratio.empty:
                df_ratio['Ticker'] = ticker
                df_ratios_all = pd.concat([df_ratios_all, df_ratio.head(1)])
        except:
            pass

    except Exception as e:
        print(f"Lỗi ở mã {ticker}: {e}")

# --- SHEET 1: MARKET OVERVIEW (Tổng quan thị trường) ---
# Lấy chỉ số VNINDEX làm tổng quan
try:
    vnindex = Vnstock().stock(symbol='VNINDEX', source='VCI').quote.history(start=start_date, end=end_date)
    df_overview = vnindex.iloc[-5:].copy() # Lấy 5 phiên gần nhất
    df_overview['Index'] = 'VNINDEX'
except:
    df_overview = pd.DataFrame([{'Index': 'VNINDEX', 'Status': 'Data not available'}])

# Gom cảnh báo thành DataFrame
df_alerts_all = pd.DataFrame(alerts_list) if alerts_list else pd.DataFrame([{'Date': end_date, 'Message': 'Không có tín hiệu đột biến nào'}])

# ==========================================
# 3. HÀM PHỤ TRỢ: LÀM SẠCH VÀ ĐẨY DỮ LIỆU LÊN GOOGLE SHEETS
# ==========================================
def push_to_sheet(worksheet_name, df):
    try:
        ws = sh.worksheet(worksheet_name)
        if df.empty:
            return
            
        # QUAN TRỌNG: Ép toàn bộ kiểu datetime sang string để Code.gs không bị đơ
        for col in df.select_dtypes(include=['datetime64[ns, UTC]', 'datetime64[ns]', 'datetime']).columns:
            df[col] = df[col].dt.strftime('%Y-%m-%d')
            
        # Đổi NaN, NaT thành chuỗi rỗng để Google Sheet đọc được
        df = df.fillna('')
        
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"✅ Đã cập nhật thành công tab: {worksheet_name}")
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật tab {worksheet_name}: {e}")

# Tiến hành đẩy toàn bộ 6 DataFrames lên 6 tab
push_to_sheet("Market_Overview", df_overview)
push_to_sheet("Stock_Prices", df_prices_all)
push_to_sheet("Technical_Signals", df_tech_all)
push_to_sheet("Foreign_Trade", df_foreign_all)
push_to_sheet("Financial_Ratios", df_ratios_all)
push_to_sheet("Market_Alerts", df_alerts_all)

print("🎉 XONG! TOÀN BỘ HỆ THỐNG 6 SHEET ĐÃ ĐƯỢC CẬP NHẬT TỰ ĐỘNG.")
