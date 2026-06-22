import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# CẤU HÌNH CƠ BẢN
# ==========================================
# ID Google Sheets của bạn:
SHEET_ID = "1r0cokW2bV7L-x8i1HWS0Cg3nOVak8VYN0vkzR5FgzNI"
CREDENTIALS_FILE = "credentials.json"
MAX_WORKERS = 3 

def process_ticker(ticker, industry):
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        
        if df is None or df.empty:
            return None
            
        current_price = df['close'].iloc[-1]
        
        df['value_ty'] = (df['close'] * df['volume']) / 1_000_000
        avg_value_ty = df['value_ty'].tail(20).mean()
        
        if current_price < 2.0 or avg_value_ty < 1.0:
            return None
            
        return {
            "Mã CK": ticker,
            "Ngành": industry,
            "Giá": round(current_price, 2),
            "Thanh Khoản (Tỷ)": round(avg_value_ty, 2)
        }
    except Exception:
        return None

def run_bot():
    print("1. Đang lấy danh sách mã...")
    try:
        companies_df = listing_companies()
        tickers_and_industries = companies_df[['ticker', 'industry']].dropna().values.tolist()
    except Exception as e:
        print("Lỗi lấy danh sách:", e)
        return

    print("2. Bắt đầu cào dữ liệu (đợi khoảng vài phút)...")
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(process_ticker, item[0], item[1]): item for item in tickers_and_industries}
        
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res is not None:
                results.append(res)
                
    if not results:
        print("Không có dữ liệu hợp lệ!")
        return

    df_results = pd.DataFrame(results).sort_values(by="Thanh Khoản (Tỷ)", ascending=False)
    
    print("3. Đang đẩy lên Google Sheets...")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(SHEET_ID).sheet1
        sheet.clear()
        
        data_to_upload = [df_results.columns.values.tolist()] + df_results.values.tolist()
        sheet.update(data_to_upload)
        print(f"✅ Xong! Đã đẩy {len(df_results)} mã lên Google Sheets thành công!")
    except Exception as e:
        print("Lỗi khi đẩy lên Google Sheets:", e)

if __name__ == "__main__":
    run_bot()
