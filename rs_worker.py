import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import stock_historical_data # Điều chỉnh hàm tùy logic cào của bạn

# --- CẤU HÌNH GOOGLE SHEETS ---
SHEET_ID = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"
CREDENTIALS_FILE = "credentials.json"

def get_stock_data():
    """
    Hàm này chứa logic cào dữ liệu của bạn.
    Dưới đây là dữ liệu giả lập (mock data) để test đường ống.
    """
    print("Đang cào dữ liệu vnstock...")
    # df = stock_historical_data(...) # Code thực tế của bạn
    
    # Mock data để ví dụ
    data = {
        "Mã CK": ["FPT", "VNM", "VCB"],
        "Giá": [115.0, 68.5, 92.0],
        "Thanh_Khoản_Tỷ": [500.5, 200.1, 350.8]
    }
    return pd.DataFrame(data)

def push_to_google_sheets(df):
    """Đẩy DataFrame lên Google Sheets bằng ID trực tiếp."""
    print("Đang kết nối với Google Sheets...")
    scope = [
        "https://spreadsheets.google.com/feeds", 
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    # Mở file trực tiếp thông qua dãy ID bạn cung cấp
    sheet = client.open_by_key(SHEET_ID).sheet1 
    
    # Xóa dữ liệu cũ của ngày hôm trước
    sheet.clear()
    
    # Chuyển DataFrame thành list-of-lists và đẩy lên sheet
    data_to_upload = [df.columns.values.tolist()] + df.values.tolist()
    sheet.update(data_to_upload)
    
    print("Đã đẩy dữ liệu thành công lên Google Sheets!")

if __name__ == "__main__":
    # 1. Thực thi việc cào
    df_result = get_stock_data()
    
    # 2. Đẩy lên file mục tiêu
    push_to_google_sheets(df_result)
