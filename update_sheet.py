import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import stock_historical_data
from datetime import datetime, timedelta
import time

# ==========================================
# 1. CẤU HÌNH KẾT NỐI GOOGLE SHEETS
# ==========================================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# Đảm bảo file credentials.json nằm cùng thư mục với file code này
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
client = gspread.authorize(CREDS)

try:
    # Kết nối vào file "chứng khoán" và sheet "data"
    worksheet = client.open("chứng khoán").worksheet("data")
    print("✅ Đã kết nối thành công tới Sheet 'data'!")
except Exception as e:
    print(f"❌ Lỗi kết nối Google Sheets: {e}")
    exit()

# ==========================================
# 2. DANH SÁCH MÃ CẦN CÀO & THỜI GIAN
# ==========================================
# Bạn có thể thêm bớt mã vào danh sách này tùy ý
tickers = ['PLX', 'VNM', 'FPT', 'SSI', 'HPG', 'MWG', 'TCB', 'VPB', 'VCB']

print(f"⏳ Đang tiến hành cào {len(tickers)} mã cổ phiếu...")

all_data = []
# Lấy lùi lại 7 ngày để đảm bảo luôn quét trúng phiên giao dịch gần nhất (tránh dính thứ 7, CN, Lễ)
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

# ==========================================
# 3. TIẾN HÀNH CÀO VÀ LỌC DỮ LIỆU
# ==========================================
for ticker in tickers:
    try:
        # Cào dữ liệu lịch sử nến ngày (1D)
        df_hist = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if not df_hist.empty:
            # Chỉ bốc dòng cuối cùng (phiên giao dịch mới nhất)
            latest = df_hist.iloc[-1]
            
            # Đóng gói đúng thứ tự và tên cột như ảnh mẫu số 2
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
            
        # Nghỉ nửa giây giữa mỗi lần cào để không bị hệ thống chặn IP
        time.sleep(0.5)
        
    except Exception as e:
        print(f"⚠️ Lỗi khi cào mã {ticker}: {e}")
        continue

# ==========================================
# 4. ĐẨY LÊN GOOGLE SHEETS
# ==========================================
if all_data:
    # Biến danh sách thành DataFrame
    df_final = pd.DataFrame(all_data)
    
    # Xóa sạch dữ liệu cũ trong tab 'data' để tránh bị đè lộn xộn
    worksheet.clear()
    
    # Chuẩn bị dữ liệu định dạng list-of-lists để đẩy lên Sheets
    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()
    
    # Đẩy lên từ ô A1
    worksheet.update('A1', data_to_upload)
    
    print(f"🎉 HOÀN TẤT! Đã đẩy {len(df_final)} hàng dữ liệu lên Google Sheets.")
else:
    print("❌ Không có dữ liệu nào được cào về.")
