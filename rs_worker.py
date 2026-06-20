import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import stock_historical_data, listing_companies
from datetime import datetime, timedelta
import time

# ==========================================
# 1. CẤU HÌNH CƠ BẢN
# ==========================================
SHEET_NAME = "Stock Fairy"  # Tên Google Sheet đích
TAB_NAME = "data"           # Tên tab con
CREDENTIALS_FILE = "credentials.json"

# ==========================================
# 2. HÀM CÀO DỮ LIỆU (QUÉT TOÀN THỊ TRƯỜNG ~1600 MÃ)
# ==========================================
def get_market_data():
    print("🚀 Đang lấy danh sách toàn bộ mã chứng khoán trên 3 sàn...")
    try:
        # Tự động lấy danh sách tất cả các mã (HOSE, HNX, UPCOM)
        df_listing = listing_companies()
        TICKERS = df_listing['ticker'].tolist()
        print(f"✅ Đã tìm thấy {len(TICKERS)} mã cổ phiếu đang niêm yết.")
    except Exception as e:
        print(f"❌ Lỗi khi lấy danh sách mã: {e}")
        return pd.DataFrame()

    print(f"🚀 Bắt đầu luồng cào dữ liệu cho {len(TICKERS)} mã...")
    
    # Lấy lùi lại 7 ngày để đảm bảo luôn quét trúng phiên giao dịch gần nhất
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d') 
    
    try:
        # Dùng VNINDEX làm thước đo kiểm tra ngày giao dịch hợp lệ gần nhất
        vnindex = stock_historical_data(symbol="VNINDEX", start_date=start_date, end_date=end_date, resolution="1D", type="index")
        
        if vnindex is None or vnindex.empty:
            print("⚠️ API vnstock hiện không trả về dữ liệu. Dừng cào để bảo vệ Sheet!")
            return pd.DataFrame()
            
        last_trading_date = str(vnindex['time'].iloc[-1])[:10]
        print(f"📅 Ngày giao dịch hợp lệ gần nhất là: {last_trading_date}")

        all_data = []
        
        # Bắt đầu vòng lặp cào từng mã cổ phiếu trong 1600 mã
        for ticker in TICKERS:
            try:
                df_hist = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
                
                if not df_hist.empty:
                    # Bốc dòng cuối cùng (ứng với phiên giao dịch mới nhất)
                    latest = df_hist.iloc[-1]
                    
                    # Đóng gói đúng định dạng 7 cột
                    row_data = {
                        'symbol': ticker,
                        'date': str(latest['time'])[:10],
                        'high': latest['high'],
                        'low': latest['low'],
                        'open': latest['open'],
                        'close': latest['close'],
                        'volume': latest['volume']
                    }
                    all_data.append(row_data)
                    print(f"   + Cào thành công: {ticker}")
                
                # NGHỈ 0.2 GIÂY: Vẫn đảm bảo không bị chặn IP mà không bắt Bot chờ quá lâu
                time.sleep(0.2)
                
            except Exception as e:
                # Bỏ qua các mã rác, mã hủy niêm yết không có dữ liệu
                # print(f"⚠️ Bỏ qua mã {ticker}") 
                continue

        return pd.DataFrame(all_data)

    except Exception as e:
        print(f"❌ Lỗi tổng trong quá trình cào dữ liệu: {e}")
        return pd.DataFrame()

# ==========================================
# 3. HÀM ĐẨY LÊN GOOGLE SHEETS
# ==========================================
def update_google_sheet(df):
    if df is None or df.empty:
        print("⚠️ Không có dữ liệu để cập nhật. Đã hủy lệnh ghi đè để bảo vệ bảng tính!")
        return

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        print("✅ Kết nối Google Sheet thành công!")

        try:
            sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Lỗi: Không tìm thấy file '{SHEET_NAME}'. Nhớ share file cho email bot nhé!")
            return
        except gspread.exceptions.WorksheetNotFound:
            print(f"❌ Lỗi: Tìm thấy file nhưng không thấy tab tên là '{TAB_NAME}'.")
            return

        # Xóa sạch dữ liệu cũ và ghi đè dữ liệu mới
        sheet.clear()
        data_to_upload = [df.columns.values.tolist()] + df.values.tolist()
        
        # Đẩy lên từ ô A1
        sheet.update('A1', data_to_upload)
        
        print(f"🎉 HOÀN TẤT! Đã đẩy thành công {len(df)} hàng dữ liệu lên Google Sheets.")

    except Exception as e:
        print(f"❌ Lỗi kết nối hoặc ghi Google Sheets: {e}")

# ==========================================
# 4. KÍCH HOẠT CHẠY CHƯƠNG TRÌNH
# ==========================================
if __name__ == "__main__":
    df_data = get_market_data()
    update_google_sheet(df_data)
