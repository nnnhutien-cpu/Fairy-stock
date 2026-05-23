import os
import json
import time
from datetime import datetime, timedelta
import gspread
import pandas as pd
import yfinance as yf
from google.oauth2.service_account import Credentials

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)

# Kết nối thẳng tới file Google Sheet của bạn
sheet = client.open('Chứng khoán').sheet1

# 2. XỬ LÝ DỮ LIỆU BẰNG YFINANCE
symbols = ['SSI','BCM','VHM','VIC','VRE','BVH','POW','GAS','ACB','BID','CTG','HDB','MBB','SHB','STB','TCB','TPB','VCB','VIB','VPB','HPG','GVR','MSN','VNM','SAB','MWG','FPT','GEX','REE','PNJ','VJC','HVN','NVL','PDR','DIG','DXG','NLG','KDH','KBC','VND','VCI','HCM','VIX','FTS','BSI','CTS','MBS','SHS','DGC','DPM','DCM','CSV','HSG','NKG','VGC','IDC','SZC','PC1','HDG','BCG','TCH','HAG','SBT','PAN','ASM','GEG','LCG','HHV','VCG','FCN','CTD','VHC','ANV','IDI','HAH','GMD','PVT','PVS','PVD','BSR','OIL','ACV','VEA','MCH','CTR','FOX','VTP', 'NAF', 'LPB', 'EVF', 'MSR', 'KDC', 'PHR', 'DCL']

data_rows = []

for sym in symbols:
    try:
        # Thêm hậu tố .VN cho mã chứng khoán Việt Nam trên Yahoo Finance
        yf_sym = f"{sym}.VN"
        ticker = yf.Ticker(yf_sym)
        
        # Lấy lịch sử 2 tháng để đảm bảo tính đủ số phiên
        df_hist = ticker.history(period="2mo")
        if df_hist.empty or len(df_hist) < 20: 
            continue
        
        df_hist = df_hist.tail(20)
        close_price_vnd = df_hist['Close'].iloc[-1]
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['Volume'].mean()
        
        # Tính GTGD và Lọc > 20 Tỷ
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        if gtgd <= 20: 
            continue

        # Lấy thông tin cơ bản an toàn (tránh lỗi nếu Yahoo thiếu thông tin mã đó)
        try:
            info = ticker.info
            market_cap_raw = info.get('marketCap', 0)
            market_cap = (market_cap_raw / 1000000000) if market_cap_raw else "N/A"
            pe = info.get('trailingPE', "N/A")
        except Exception:
            market_cap = "N/A"
            pe = "N/A"
        
        # Tính toán xu hướng dựa trên đường MA20
        ma20 = df_hist['Close'].mean()
        trend = "KHẢ QUAN" if close_price_vnd > ma20 else "TRUNG TÍNH"
        tech_score = 5 if close_price_vnd > ma20 else 2
            
        data_rows.append([
            sym, 
            round(close_kvnd, 2), 
            int(avg_vol_20), 
            tech_score, 
            trend,
            round(market_cap, 0) if isinstance(market_cap, (int, float)) else market_cap,
            round(pe, 1) if isinstance(pe, (int, float)) else pe, 
            round(gtgd, 1)
        ])
        time.sleep(0.5) # Tránh bị Yahoo chặn IP khi gửi yêu cầu liên tục
    except Exception:
        continue

# 3. ĐẨY DỮ LIỆU MỚI LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']

if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("Đã cập nhật dữ liệu thành công.")
else:
    print("Không có dữ liệu nào thỏa mãn điều kiện lọc.")
