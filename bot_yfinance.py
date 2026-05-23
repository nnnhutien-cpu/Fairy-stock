# FORCE UPDATE YFINANCE - VERSION 4.1 QUÉT TOÀN THỊ TRƯỜNG & SÀN
import os
import json
import time
import requests
import pandas as pd
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)
sheet = client.open('Chứng khoán').sheet1

# 2. LẤY DANH SÁCH MÃ TỪ 3 SÀN
print("Đang lấy danh sách toàn bộ mã chứng khoán...")
try:
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock&size=3000"
    response = requests.get(url, headers=headers)
    data = response.json().get('data', [])
    symbols = [item['symbol'] for item in data if len(item['symbol']) == 3]
except Exception:
    symbols = ['SSI','HPG','VNM','VCB','VIC','VHM','MWG','FPT','ACB','MBB','TCB','STB','SHB','VND','VCI','NVL','PDR','DIG','DXG']

symbols = list(set(symbols))

# 3. QUÉT DỮ LIỆU & LỌC > 5 TỶ
data_rows = []
print("Bắt đầu quét...")

for sym in symbols:
    try:
        ticker = yf.Ticker(f"{sym}.VN")
        df_hist = ticker.history(period="2mo")
        if df_hist.empty or len(df_hist) < 20:
            continue

        df_hist = df_hist.tail(20)
        close_price_vnd = df_hist['Close'].iloc[-1]
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['Volume'].mean()
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        
        # Hạ ngưỡng lọc xuống 5 tỷ để lấy thêm HNX/UPCoM
        if gtgd <= 5:
            continue

        try:
            info = ticker.info
            market_cap_raw = info.get('marketCap', 0)
            market_cap = (market_cap_raw / 1000000000) if market_cap_raw else "N/A"
            pe = info.get('trailingPE', "N/A")
            exchange = info.get('exchange', 'N/A') # Lấy tên sàn
        except Exception:
            market_cap, pe, exchange = "N/A", "N/A", "N/A"

        ma20 = df_hist['Close'].mean()
        trend = "KHẢ QUAN" if close_price_vnd > ma20 else "TRUNG TÍNH"
        tech_score = 5 if close_price_vnd > ma20 else 2

        data_rows.append([
            sym, exchange, round(close_kvnd, 2), int(avg_vol_20), tech_score, trend,
            round(market_cap, 0) if isinstance(market_cap, float) else market_cap,
            round(pe, 1) if isinstance(pe, float) else pe, round(gtgd, 1)
        ])
        time.sleep(0.1)
    except Exception:
        continue

# 4. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Sàn', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"THÀNH CÔNG: Đã đẩy {len(data_rows)} mã!")
else:
    print("CẢNH BÁO: Không có dữ liệu!")
