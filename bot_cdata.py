import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import stock_historical_data
from datetime import datetime, timedelta
import time
import sys

# ==========================================
# 1. CẤU HÌNH KẾT NỐI BẰNG ID (CHỐNG LỖI 100%)
# ==========================================
SHEET_ID = "1r0cokW2bV7L-x8i1HWS0Cg3nOVak8VYN0vkzR5FgzNI"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Đảm bảo file credentials.json nằm cùng thư mục
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
client = gspread.authorize(CREDS)

try:
    # DÙNG ID THAY VÌ TÊN ĐỂ KHÔNG BAO GIỜ SỢ ĐỔI TÊN BỊ LỖI
    worksheet = client.open_by_key(SHEET_ID).worksheet("data")
    print("✅ Đã kết nối thành công tới Sheet 'data'!")
except Exception as e:
    print(f"❌ Lỗi kết nối Google Sheets: {e}")
    sys.exit(1) # Báo lỗi đỏ cho GitHub biết để dừng lại

# ==========================================
# 2. DANH SÁCH MÃ CẦN CÀO & THỜI GIAN
# ==========================================
tickers = ['PLX', 'VNM', 'FPT', 'SSI', 'HPG', 'MWG', 'TCB', 'VPB', 'VCB']
print(f"⏳ Đang tiến hành cào {len(tickers)} mã cổ phiếu...")

all_data = []
# Lấy lùi lại 7 ngày để đảm bảo luôn quét trúng phiên giao dịch gần nhất
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

# ==========================================
# 3. TIẾN HÀNH CÀO VÀ LỌC DỮ LIỆU
# ==========================================
for ticker in tickers:
    try:
        df_hist = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df_hist is not None and not df_hist.empty:
            latest = df_hist.iloc[-1]
            
            row_data = {
                'symbol': ticker,
                'date': str(latest['time'])[:10], # Chỉ lấy YYYY-MM-DD
                'high': latest['high'],
                'low': latest['low'],
                'open': latest['open'],
                'close': latest['close'],
                'volume': latest['volume']
            }
            all_data.append(row_data)
            print(f"   + Cào thành công: {ticker}")
            
        time.sleep(0.5) # Nghỉ nửa giây chống block IP
        
    except Exception as e:
        print(f"⚠️ Lỗi khi cào mã {ticker}: {e}")
        continue

# ==========================================
# 4. ĐẨY LÊN GOOGLE SHEETS
# ==========================================
if all_data:
    df_final = pd.DataFrame(all_data)
    worksheet.clear()
    
    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()
    
    # Đẩy lên Google Sheet chuẩn phiên bản mới
    worksheet.update(values=data_to_upload, range_name='A1')
    
    print(f"🎉 HOÀN TẤT! Đã đẩy {len(df_final)} hàng dữ liệu lên Google Sheets.")
else:
    print("❌ Không có dữ liệu nào được cào về.")
    sys.exit(1)
