import os
import json
import gspread
from google.oauth2.service_account import Credentials
from vnstock import price_board, stock_historical_data  # CHỈ DÙNG THƯ VIỆN VNSTOCK
import pandas as pd
from datetime import datetime

# 1. CẤU HÌNH KẾT NỐI GOOGLE SHEETS
# Lấy Key từ GitHub Secrets
creds_json = os.environ.get('GCP_SA_KEY')
if not creds_json:
    raise ValueError("Không tìm thấy GCP_SA_KEY trong GitHub Secrets. Vui lòng kiểm tra lại!")

scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(creds_json)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

# Kết nối thẳng vào file Sheets bằng ID bạn cung cấp
SHEET_ID = '1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY'
sheet = client.open_by_key(SHEET_ID).sheet1  # Ghi vào Tab đầu tiên của Sheet

print("Đang khởi động cỗ máy lấy dữ liệu THUẦN TÚY từ vnstock...")

try:
    # 2. LẤY DỮ LIỆU TỪ VNSTOCK (Tuyệt đối không dùng Request ngoài)
    # Ở đây tôi dùng price_board('VN30') làm ví dụ chuẩn của vnstock 0.2.8.2. 
    # Bạn hoàn toàn có thể thay bằng hàm stock_historical_data() nếu muốn lấy lịch sử.
    df = price_board('VN30')
    
    if not df.empty:
        # Xử lý dữ liệu: Ép tất cả về định dạng chữ (String) để Google Sheets không báo lỗi JSON
        df = df.fillna("").astype(str)
        
        # Đóng gói dữ liệu thành danh sách (List of lists)
        data_to_upload = [df.columns.values.tolist()] + df.values.tolist()
        
        # 3. XÓA CŨ - GHI ĐÈ MỚI VÀO GOOGLE SHEETS
        sheet.clear()
        sheet.update('A1', data_to_upload)
        print(f"✅ Đã cập nhật thành công {len(df)} dòng dữ liệu lên Google Sheets lúc {datetime.now()}!")
    else:
        print("⚠️ Dữ liệu vnstock trả về bị trống.")

except Exception as e:
    print(f"❌ Lỗi trong quá trình chạy vnstock hoặc ghi Sheets: {e}")
