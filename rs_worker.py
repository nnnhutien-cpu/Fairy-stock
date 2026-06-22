import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ==========================================
# CẤU HÌNH BỘ LỌC VÀ HỆ THỐNG
# ==========================================
MIN_LIQUIDITY = 1.0  # Tối thiểu 1 tỷ VNĐ/phiên
MIN_PRICE = 2.0      # Tối thiểu giá 2,000 VNĐ
SHEET_NAME = "Stock Fairy"
TAB_NAME = "Sheet1"
SHEET_ID = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"
CREDENTIALS_FILE = "credentials.json"
MAX_WORKERS = 5      # Giảm xuống 5 luồng để tránh bị nhà cung cấp dữ liệu chặn IP (gây rỗng bảng)

# --- TẦNG 1 & 2: LỌC THANH KHOẢN VÀ GIÁ ---
def process_ticker(ticker, industry):
    try:
        # Lấy dữ liệu khoảng 30-40 ngày để tính trung bình 20 phiên gần nhất
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
        
        # Cào dữ liệu lịch sử
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df is None or df.empty or len(df) == 0:
            return None
            
        if 'close' not in df.columns or 'volume' not in df.columns:
            return None
            
        # --- TÍNH TOÁN DỮ LIỆU ---
        current_price = df['close'].iloc[-1]
        
        # Đổi giá trị giao dịch ra đơn vị TỶ VNĐ
        # Công thức chuẩn: (Giá * Khối lượng) / 1,000,000
        df['value_ty'] = (df['close'] * df['volume']) / 1_000_000
        
        # Tính trung bình 20 phiên gần nhất
        avg_value_ty = df['value_ty'].tail(20).mean()
        
        # BỘ LỌC ĐIỀU KIỆN KÝ THUẬT VÀ GIÁ
        if current_price < MIN_PRICE:
            return None
        if avg_value_ty < MIN_LIQUIDITY:
            return None
            
        return {
            "Mã CK": ticker,
            "Ngành": industry,
            "Giá": round(current_price, 2),
            "Thanh_Khoản_Tỷ": round(avg_value_ty, 2)
        }
    except Exception:
        return None

def run_pipeline():
    print("1. Đang tải danh sách công ty tổng từ Vnstock...")
    try:
        companies_df = listing_companies()
        if companies_df is None or companies_df.empty:
            print("❌ Không lấy được danh sách công ty từ Vnstock.")
            return
        companies_df = companies_df[['ticker', 'industry']].dropna()
        tickers_and_industries = companies_df.values.tolist()
    except Exception as e:
        print(f"❌ Lỗi kết nối danh sách công ty: {e}")
        return

    print(f"2. Khởi động {MAX_WORKERS} luồng quét song song cho {len(tickers_and_industries)} mã...")
    results = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {
            executor.submit(process_ticker, item[0], item[1]): item 
            for item in tickers_and_industries
        }
        
        for future in tqdm(as_completed(future_to_ticker), total=len(tickers_and_industries)):
            res = future.result()
            if res is not None:
                results.append(res)
                
    if not results:
        print("⚠️ Cảnh báo: Không có mã nào thỏa mãn bộ lọc hoặc API bị nghẽn hoàn toàn!")
        return
        
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="Thanh_Khoản_Tỷ", ascending=False)
    
    print(f"✅ Đã lọc thành công {len(df_results)} mã. Đang tiến hành đẩy lên Google Sheets...")
    
    # --- ĐẨY LÊN GOOGLE SHEETS THEO TÊN FILE VÀ TÊN TAB CHUẨN ---
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        # Bước A: Tìm file Google Sheet (Ưu tiên ID, nếu không được sẽ tìm bằng Tên)
        try:
            spreadsheet = client.open_by_key(SHEET_ID)
            print(f"-> Đã kết nối thành công file qua ID: {SHEET_ID}")
        except Exception:
            spreadsheet = client.open(SHEET_NAME)
            print(f"-> Đã kết nối thành công file qua Tên: '{SHEET_NAME}'")
            
        # Bước B: Tìm chính xác tab "sheet 1" (Bẫy lỗi chữ hoa/thường để tránh lỗi treo bot)
        sheet = None
        for test_name in [TAB_NAME, "Sheet1", "sheet1", "Sheet 1"]:
            try:
                sheet = spreadsheet.worksheet(test_name)
                print(f"-> Đã nhận diện đúng Tab: '{test_name}'")
                break
            except Exception:
                continue
                
        if sheet is None:
            sheet = spreadsheet.sheet1
            print("-> Không tìm thấy tab tên 'sheet 1', tự động chọn Tab mặc định đầu tiên để ghi dữ liệu.")
            
        # Ghi đè dữ liệu mới
        sheet.clear()
        data_to_upload = [df_results.columns.values.tolist()] + df_results.values.tolist()
        sheet.update(data_to_upload)
        
        print("🚀 THÀNH CÔNG RỰC RỠ! Dữ liệu đã xuất hiện chuẩn chỉnh trên Google Sheets!")
    except Exception as e:
        print(f"❌ Lỗi trong quá trình tương tác Google Sheets: {e}")

if __name__ == "__main__":
    run_pipeline()
