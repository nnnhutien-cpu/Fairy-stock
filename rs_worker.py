import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
MIN_LIQUIDITY = 1.0  # Tối thiểu 10 tỷ VNĐ/phiên
MIN_PRICE = 2.0      # Tối thiểu giá 10,000 VNĐ
SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"  # ID từ link Sheet của bạn
CREDENTIALS_FILE = "credentials.json"
MAX_WORKERS = 10

def process_ticker(ticker, industry, current_price, avg_value):
    # Điểm kỹ thuật nhanh - Giữ nguyên cấu trúc hàm bạn yêu cầu
    return {
        "Mã CK": ticker,
        "Ngành": industry,
        "Giá": current_price,
        "Thanh_Khoản_Tỷ": round(avg_value / 1000, 2)
    }

def fetch_and_filter(row):
    ticker = row['ticker']
    industry = row.get('industry', 'Chưa rõ')
    
    try:
        # Lấy dữ liệu 20 phiên gần nhất để tính thanh khoản trung bình
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        df_hist = stock_historical_data(ticker, start_date, end_date, resolution='1D', type='stock')
        
        if df_hist is not None and not df_hist.empty:
            # Chuẩn hóa tên cột viết thường
            df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
            
            # Tính giá hiện tại và thanh khoản (Khối lượng * Giá đóng cửa)
            current_price = df_hist['close'].iloc[-1]
            
            # Tính giá trị giao dịch trung bình (đơn vị tỷ VNĐ nếu vnstock trả về giá trị thô)
            # Thông thường cột 'match_value' hoặc 'volume' * 'close'
            if 'match_value' in df_hist.columns:
                avg_value = df_hist['match_value'].mean() / 1_000_000_000
            else:
                avg_value = (df_hist['volume'] * df_hist['close']).mean() / 1_000_000_000
            
            # TẦNG 1 & 2: LỌC THANH KHOẢN VÀ GIÁ
            if current_price >= (MIN_PRICE * 1000) and avg_value >= MIN_LIQUIDITY:
                return process_ticker(ticker, industry, current_price, avg_value)
    except Exception:
        pass
    return None

def main():
    print("🕵️ Đang khởi động Bot quét sàn lọc cổ phiếu...")
    
    # 1. Kết nối Google Sheets qua file JSON quyền hạn
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_KEY)
        sheet = spreadsheet.get_worksheet(0) # Lấy Sheet đầu tiên
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return

    # 2. Lấy danh sách toàn bộ cổ phiếu đang niêm yết
    df_companies = listing_companies()
    if df_companies is empty or df_companies is None:
        print("❌ Không lấy được danh sách công ty từ vnstock!")
        return
        
    records = df_companies.to_dict('records')
    final_results = []
    
    # 3. Quét đa luồng an toàn tốc độ cao
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_and_filter, row): row for row in records}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Quét mã"):
            res = future.result()
            if res is not None:
                final_results.append(res)
                
    # 4. Đẩy dữ liệu sạch lên Google Sheet
    if final_results:
        df_output = pd.DataFrame(final_results)
        
        # Xóa dữ liệu cũ và ghi đè dữ liệu mới
        sheet.clear()
        # Cập nhật cả Tiêu đề cột và Dữ liệu
        sheet.update([df_output.columns.values.tolist()] + df_output.values.tolist())
        print(f"✅ Đã cập nhật thành công {len(df_output)} mã đạt tiêu chuẩn lên Google Sheet!")
    else:
        print("⚠️ Không có mã nào đạt tiêu chuẩn lọc hôm nay.")

if __name__ == "__main__":
    main()
