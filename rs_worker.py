import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# CẤU HÌNH BỘ LỌC VÀ HỆ THỐNG
# ==========================================
MIN_LIQUIDITY = 1.0  # Tối thiểu 1 tỷ VNĐ/phiên
MIN_PRICE = 2.0      # Tối thiểu giá 2,000 VNĐ (trên bảng điện là 2.0)
SHEET_ID = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"
CREDENTIALS_FILE = "credentials.json"
MAX_WORKERS = 10     # Số luồng chạy song song

# --- TẦNG 1 & 2: LỌC THANH KHOẢN VÀ GIÁ ---
def process_ticker(ticker, industry):
    try:
        # Lấy dữ liệu 20 ngày gần nhất để tính trung bình thanh khoản
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Lấy dữ liệu lịch sử của mã
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df is None or df.empty or len(df) == 0:
            return None
            
        # --- TÍNH TOÁN DỮ LIỆU ---
        # Giá hiện tại (chốt phiên gần nhất)
        current_price = df['close'].iloc[-1]
        
        # Tính thanh khoản (Giá trị giao dịch)
        # vnstock trả về 'close' theo đơn vị nghìn VNĐ, 'volume' là số cổ phiếu.
        # Công thức Tỷ VNĐ = (Giá * Volume * 1000) / 1,000,000,000 = (Giá * Volume) / 1,000,000
        df['value_ty'] = (df['close'] * df['volume']) / 1_000_000
        
        # Thanh khoản trung bình 20 phiên
        avg_value_ty = df['value_ty'].tail(20).mean()
        
        # BỘ LỌC
        if current_price < MIN_PRICE:
            return None
            
        if avg_value_ty < MIN_LIQUIDITY:
            return None
            
        # Trả về format từ điển chuẩn theo yêu cầu của bạn
        return {
            "Mã CK": ticker,
            "Ngành": industry,
            "Giá": round(current_price, 2),
            "Thanh_Khoản_Tỷ": round(avg_value_ty, 2)
        }
    except Exception as e:
        return None

def run_pipeline():
    print("1. Đang lấy danh sách mã và nhóm ngành từ Vnstock...")
    try:
        companies_df = listing_companies()
        # Lấy đúng 2 cột cần thiết và loại bỏ dữ liệu rỗng
        companies_df = companies_df[['ticker', 'industry']].dropna()
        tickers_and_industries = companies_df.values.tolist()
    except Exception as e:
        print(f"Lỗi lấy danh sách công ty: {e}")
        return

    print(f"2. Khởi động {MAX_WORKERS} luồng cào dữ liệu cho {len(tickers_and_industries)} mã...")
    results = []
    
    # Chạy đa luồng để cào nhanh hơn
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Giao việc cho các luồng
        future_to_ticker = {
            executor.submit(process_ticker, item[0], item[1]): item 
            for item in tickers_and_industries
        }
        
        # Thu thập kết quả
        for future in tqdm(as_completed(future_to_ticker), total=len(tickers_and_industries)):
            res = future.result()
            if res is not None:
                results.append(res)
                
    if not results:
        print("Cảnh báo: Không có mã nào vượt qua được bộ lọc!")
        return
        
    # Tạo bảng dữ liệu và sắp xếp cho đẹp (Từ thanh khoản cao nhất xuống thấp nhất)
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="Thanh_Khoản_Tỷ", ascending=False)
    
    print(f"✅ Đã lọc thành công {len(df_results)} mã. Bắt đầu đẩy lên Google Sheets...")
    
    # Đẩy lên Sheet
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        # Kết nối bằng ID file của bạn
        sheet = client.open_by_key(SHEET_ID).sheet1
        sheet.clear()
        
        # Đẩy tiêu đề cột và nội dung dữ liệu
        data_to_upload = [df_results.columns.values.tolist()] + df_results.values.tolist()
        sheet.update(data_to_upload)
        
        print("🚀 BÙM! Dữ liệu đã được ném thẳng vào Google Sheets thành công!")
    except Exception as e:
        print(f"Lỗi khi đẩy dữ liệu lên Google Sheets: {e}")

if __name__ == "__main__":
    run_pipeline()
