import pandas as pd
import numpy as np
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
MIN_LIQUIDITY_TY = 10.0  # Tối thiểu 10 tỷ VNĐ/phiên
MIN_PRICE_VND = 10000.0   # Tối thiểu giá 10,000 VNĐ
SPREADSHEET_KEY = "1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY"  # ID từ link Sheet của bạn
CREDENTIALS_FILE = "credentials.json"
MAX_WORKERS = 5 # Giảm xuống 5 luồng để các công ty chứng khoán không block IP của GitHub

def process_ticker(ticker, industry, current_price, avg_value_ty):
    return {
        "Mã CK": ticker,
        "Ngành": industry,
        "Giá": int(current_price),
        "Thanh_Khoản_Tỷ": round(avg_value_ty, 2)
    }

def fetch_and_filter(row):
    ticker = row['ticker']
    industry = row.get('industry', 'Chưa rõ')
    
    # Thử gọi API tối đa 3 lần nếu bị nghẽn mạng
    for attempt in range(3):
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            df_hist = stock_historical_data(ticker, start_date, end_date, resolution='1D', type='stock')
            
            if df_hist is not None and not df_hist.empty:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                # Lấy giá đóng cửa phiên gần nhất
                current_price = df_hist['close'].iloc[-1]
                
                # Tính toán giá trị giao dịch trung bình chuẩn xác
                # Một số phiên bản vnstock trả về cột 'match_value' hoặc 'value'
                if 'match_value' in df_hist.columns:
                    avg_value_raw = df_hist['match_value'].mean()
                elif 'value' in df_hist.columns:
                    avg_value_raw = df_hist['value'].mean()
                else:
                    # Nếu không có cột giá trị, tự tính bằng Khối lượng * Giá đóng cửa
                    avg_value_raw = (df_hist['volume'] * df_hist['close']).mean()
                
                # Chuẩn hóa đơn vị về TỶ đồng
                # Nếu vnstock trả về đơn vị thô (ví dụ: 28 tỷ = 28,000,000,000)
                if avg_value_raw > 1_000_000:
                    avg_value_ty = avg_value_raw / 1_000_000_000
                else:
                    # Nếu vnstock đã tự chia cho 1000 sẵn
                    avg_value_ty = avg_value_raw / 1_000
                
                # Ép giá về đơn vị đồng (nếu vnstock trả về dạng 28.5 thay vì 28500)
                if current_price < 1000:
                    current_price_vnd = current_price * 1000
                else:
                    current_price_vnd = current_price

                # --- ĐIỀU KIỆN LỌC CHUẨN XÁC ---
                if current_price_vnd >= MIN_PRICE_VND and avg_value_ty >= MIN_LIQUIDITY_TY:
                    return process_ticker(ticker, industry, current_price_vnd, avg_value_ty)
                
                break # Thành công thì thoát vòng lặp attempt
        except Exception:
            time.sleep(1) # Nghỉ 1 giây rồi thử lại
            pass
    return None

def main():
    print("🕵️ Đang khởi động Bot quét sàn lọc cổ phiếu Cô Tiên Stock...")
    
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_KEY)
        sheet = spreadsheet.get_worksheet(0)
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return

    df_companies = listing_companies()
    if df_companies is None or df_companies.empty:
        print("❌ Không lấy được danh sách công ty từ vnstock!")
        return
        
    records = df_companies.to_dict('records')
    final_results = []
    
    # Quét đa luồng điều chỉnh tốc độ an toàn chống chặn IP
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_and_filter, row): row for row in records}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Quét mã toàn sàn"):
            res = future.result()
            if res is not None:
                final_results.append(res)
                
    if final_results:
        df_output = pd.DataFrame(final_results)
        # Sắp xếp theo thanh khoản giảm dần cho dễ nhìn
        df_output = df_output.sort_values(by='Thanh_Khoản_Tỷ', ascending=False)
        
        sheet.clear()
        sheet.update([df_output.columns.values.tolist()] + df_output.values.tolist())
        print(f"✅ Đã cập nhật thành công {len(df_output)} mã CHẤT LƯỢNG CAO lên Google Sheet!")
    else:
        print("⚠️ Không có mã niêm yết nào thỏa mãn điều kiện lọc (Giá > 10k & Vol > 10 tỷ).")

if __name__ == "__main__":
    main()
