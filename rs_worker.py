import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
import time

# ==========================================
# CẤU HÌNH CƠ BẢN
# ==========================================
# Bạn đã đổi tên thành Stock Fairy (Lưu ý: Khuyên dùng ID Google Sheet nếu có thể để chống lỗi đổi tên)
SHEET_NAME = "Stock Fairy" 
TAB_NAME = "data" # Tên tab (sheet con) bên trong file
CREDENTIALS_FILE = "credentials.json"

MIN_LIQUIDITY = 1.0  # Tối thiểu 1 tỷ VNĐ/phiên
MIN_PRICE = 2.0      # Tối thiểu giá 2,000 VNĐ

def get_market_data():
    """Hàm cào dữ liệu thông minh, tự lùi ngày nếu cuối tuần"""
    print("🚀 Bot đang bốc dữ liệu 5 cột chuẩn...")
    try:
        # Lấy danh sách tất cả mã CK (Bỏ qua các mã OTC hoặc hủy niêm yết)
        df_listing = listing_companies()
        
        # Nếu đang là Thứ 7, Chủ Nhật hoặc ngoài giờ, API có thể rỗng
        # Khắc phục: Lấy dữ liệu lịch sử của ngày giao dịch gần nhất
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d') 
        
        # Lấy thử dữ liệu VNINDEX để kiểm tra ngày giao dịch cuối cùng có data
        vnindex = stock_historical_data("VNINDEX", start_date, end_date, "1D", "index")
        
        if vnindex is None or vnindex.empty:
            print("⚠️ API vnstock hiện không trả về dữ liệu lịch sử tổng.")
            return pd.DataFrame()
            
        last_trading_date = vnindex['time'].iloc[-1]
        print(f"📅 Ngày giao dịch hợp lệ gần nhất được lấy dữ liệu: {last_trading_date}")

        # --- CHÚ Ý: ĐOẠN NÀY LÀ LOGIC LỌC/CÀO DỮ LIỆU CỦA BẠN ---
        # Do không có toàn bộ file cũ của bạn, đây là phần giả lập cào dữ liệu mẫu 5 cột
        # Bạn có thể thay phần này bằng vòng lặp cào chi tiết của bạn
        
        # Giả sử chúng ta ghép data thành công:
        df_final = pd.DataFrame({
            "Mã CK": ["HPG", "SSI", "VND", "FPT"],
            "Giá": [29.5, 35.0, 22.1, 130.5],
            "Khối Lượng": [15000000, 12000000, 8000000, 3000000],
            "Xu Hướng": ["Tăng", "Tăng", "Giảm", "Tăng"],
            "Rating": ["A", "B", "C", "A+"]
        })
        
        return df_final

    except Exception as e:
        print(f"❌ Lỗi trong quá trình cào dữ liệu: {e}")
        return pd.DataFrame()

def update_google_sheet(df):
    """Kết nối và đẩy dữ liệu lên Google Sheets"""
    try:
        # Định nghĩa quyền truy cập
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        print("✅ Kết nối Google Sheet thành công!")

        if df is None or df.empty:
            print("⚠️ Không có dữ liệu sau khi lọc (Hoặc API bị chặn). Đã hủy lệnh ghi đè để bảo vệ bảng tính!")
            return

        # Kết nối tới tên mới "Stock Fairy"
        try:
            sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Lỗi: Không tìm thấy file Google Sheet nào có tên là '{SHEET_NAME}'.")
            print("💡 Gợi ý: Hãy kiểm tra lại xem bạn đã Share file này cho email của Bot chưa?")
            return
        except gspread.exceptions.WorksheetNotFound:
            print(f"❌ Lỗi: Tìm thấy file '{SHEET_NAME}' nhưng không thấy tab tên là '{TAB_NAME}'.")
            return

        # Xóa dữ liệu cũ và cập nhật dữ liệu mới
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"🎉 Cập nhật thành công {len(df)} hàng dữ liệu vào '{SHEET_NAME}'!")

    except Exception as e:
        print(f"❌ Lỗi kết nối hoặc ghi Google Sheets: {e}")

if __name__ == "__main__":
    df_data = get_market_data()
    update_google_sheet(df_data)
