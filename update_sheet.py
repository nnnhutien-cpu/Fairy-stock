import os
import json
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials # Thay thế an toàn cho oauth2client
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. CẤU HÌNH KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_SA_KEY')
if not creds_json:
    raise ValueError("Không tìm thấy GCP_SA_KEY trong GitHub Secrets!")

scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(creds_json)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

SHEET_ID = '1_RC7uZDEbnWpS7pOMSwMToJ2eVW4gj3Mmjrsglz7skY'
sheet = client.open_by_key(SHEET_ID).sheet1

print("🚀 Đang khởi động cỗ máy cào dữ liệu Đa Luồng từ vnstock...")

# 2. LẤY DANH SÁCH MÃ CHỨNG KHOÁN (listing_companies)
try:
    df_listing = listing_companies()
    # Lấy ra danh sách các mã trên sàn HOSE, HNX, UPCOM
    all_tickers = df_listing['ticker'].tolist()
    # Giới hạn lấy thử 50 mã đầu tiên để tránh bị quá tải API Google Sheet trong lần chạy đầu
    tickers_to_fetch = all_tickers[:50] 
    print(f"Bắt đầu quét {len(tickers_to_fetch)} mã cổ phiếu...")
except Exception as e:
    print(f"Lỗi khi lấy danh sách công ty: {e}")
    tickers_to_fetch = []

# Cài đặt thời gian: Lấy dữ liệu 30 ngày gần nhất
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

# Hàm worker để chạy đa luồng
def fetch_data_for_ticker(ticker):
    try:
        # Dùng historical data của vnstock 0.2.8.2
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        if df is not None and not df.empty:
            df['Ticker'] = ticker # Thêm cột tên mã
            return df
    except:
        pass
    return pd.DataFrame()

# 3. CHẠY ĐA LUỒNG (ThreadPoolExecutor & tqdm)
all_data_frames = []
with ThreadPoolExecutor(max_workers=10) as executor:
    # Giao việc cho các luồng và hiển thị thanh tiến trình tqdm
    future_to_ticker = {executor.submit(fetch_data_for_ticker, ticker): ticker for ticker in tickers_to_fetch}
    for future in tqdm(as_completed(future_to_ticker), total=len(tickers_to_fetch), desc="Đang tải dữ liệu"):
        result_df = future.result()
        if not result_df.empty:
            all_data_frames.append(result_df)

# 4. GỘP DỮ LIỆU VÀ ĐẨY LÊN GOOGLE SHEETS
if all_data_frames:
    final_df = pd.concat(all_data_frames, ignore_index=True)
    
    # Xử lý NaN của numpy và ép kiểu string để Sheets không lỗi
    final_df = final_df.replace({np.nan: ""}).astype(str)
    
    data_to_upload = [final_df.columns.values.tolist()] + final_df.values.tolist()
    
    sheet.clear()
    sheet.update('A1', data_to_upload)
    print(f"\n✅ Đã đẩy thành công {len(final_df)} dòng dữ liệu của {len(tickers_to_fetch)} mã lên Google Sheets!")
else:
    print("\n⚠️ Không thu thập được dữ liệu nào.")
