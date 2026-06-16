import pandas as pd
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
SPREADSHEET_KEY = "1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc"  # Đã thay ID Google Sheet mới của bạn
CREDENTIALS_FILE = "credentials.json"
MAX_WORKERS = 5 # Giữ ở mức 5 luồng để API không bị sập

def fetch_data(row):
    ticker = row['ticker']
    industry = row.get('industry', 'Chưa rõ')
    
    for attempt in range(3):
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
            
            # Cào dữ liệu từ vnstock
            df_hist = stock_historical_data(ticker, start_date, end_date, resolution='1D', type='stock')
            
            if df_hist is not None and not df_hist.empty:
                df_hist.columns = [str(c).lower().strip() for c in df_hist.columns]
                
                current_price = df_hist['close'].iloc[-1]
                volume = df_hist['volume'].iloc[-1]
                
                # Ép giá về đơn vị VNĐ chuẩn
                if current_price < 1000:
                    current_price = current_price * 1000
                    
                # Trả về 1 dòng dữ liệu
                return {
                    "Mã CK": ticker,
                    "Ngành": industry,
                    "Giá Đóng Cửa": int(current_price),
                    "Khối Lượng": int(volume),
                    "Ngày Cập Nhật": end_date
                }
            break # Thành công thì thoát vòng lặp
        except Exception:
            time.sleep(1) # Bị chặn thì nghỉ 1 giây rồi thử lại
            pass
    return None

def main():
    print("🕵️ Đang cào dữ liệu Vnstock và đẩy lên Google Sheet...")
    
    # 1. Kết nối Google Sheet
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_KEY)
        sheet = spreadsheet.get_worksheet(0) # Ghi vào Sheet đầu tiên (Sheet1)
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return

    # 2. Lấy danh sách công ty
    df_companies = listing_companies()
    if df_companies is None or df_companies.empty:
        print("❌ Lỗi: Không lấy được danh sách mã CK!")
        return
        
    records = df_companies.to_dict('records')
    final_results = []
    
    # 3. Quét tốc độ cao
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_data, row): row for row in records[:50]} # TEST 50 MÃ ĐẦU TIÊN (Bạn có thể bỏ [:50] để quét toàn sàn)
        for future in tqdm(as_completed(futures), total=len(futures), desc="Đang cào dữ liệu"):
            res = future.result()
            if res is not None:
                final_results.append(res)
                
    # 4. Ghi đè dữ liệu lên Google Sheet
    if final_results:
        df_output = pd.DataFrame(final_results)
        sheet.clear() # Xóa trắng dữ liệu cũ
        sheet.update([df_output.columns.values.tolist()] + df_output.values.tolist()) # Đổ dữ liệu mới vào
        print(f"✅ Đã đổ thành công {len(df_output)} dòng dữ liệu lên Google Sheet!")
    else:
        print("⚠️ Không cào được dữ liệu nào.")

if __name__ == "__main__":
    main()
