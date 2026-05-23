import os
import json
import time
from datetime import datetime, timedelta
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from vnstock import stock_historical_data, ticker_overview

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)

# QUAN TRỌNG: SỬA TÊN BÊN DƯỚI THÀNH TÊN FILE GOOGLE SHEET CỦA BẠN
sheet = client.open('Chứng khoán').sheet1 

# 2. XỬ LÝ DỮ LIỆU
end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
symbols = ['SSI','BCM','VHM','VIC','VRE','BVH','POW','GAS','ACB','BID','CTG','HDB','MBB','SHB','STB','TCB','TPB','VCB','VIB','VPB','HPG','GVR','MSN','VNM','SAB','MWG','FPT','GEX','REE','PNJ','VJC','HVN','NVL','PDR','DIG','DXG','NLG','KDH','KBC','VND','VCI','HCM','VIX','FTS','BSI','CTS','MBS','SHS','DGC','DPM','DCM','CSV','HSG','NKG','VGC','IDC','SZC','PC1','HDG','BCG','TCH','HAG','SBT','PAN','ASM','GEG','LCG','HHV','VCG','FCN','CTD','VHC','ANV','IDI','HAH','GMD','PVT','PVS','PVD','BSR','OIL','ACV','VEA','MCH','CTR','FOX','ViettelPost', 'NAF', 'LPB', 'EVF', 'MSR', 'KDC', 'PHR', 'DCL']

data_rows = []

for sym in symbols:
    try:
        df_hist = stock_historical_data(symbol=sym, start_date=start_date, end_date=end_date, resolution='1D', type='stock')
        if df_hist is None or df_hist.empty or len(df_hist) < 20: continue
        
        df_hist = df_hist.sort_values('time').tail(20)
        close_price_vnd = df_hist['close'].iloc[-1]
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['volume'].mean()
        
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        if gtgd <= 20: continue

        overview = ticker_overview(sym)
        market_cap = overview['marketcap'].iloc[0] if not overview.empty else 0
        pe = overview['pe'].iloc[0] if not overview.empty else 0
        
        ma20 = df_hist['close'].mean()
        trend = "KHẢ QUAN" if close_price_vnd > ma20 else "TRUNG TÍNH"
        tech_score = 5 if close_price_vnd > ma20 else 2
            
        data_rows.append([
            sym, round(close_kvnd, 2), int(avg_vol_20), tech_score, trend,
            round(market_cap, 0) if pd.notnull(market_cap) else "N/A",
            round(pe, 1) if pd.notnull(pe) else "N/A", round(gtgd, 1)
        ])
        time.sleep(0.5) 
    except Exception:
        continue

# 3. ĐẨY LÊN GOOGLE SHEET
columns = ['Mã (đơn vị)', 'Đóng cửa (kvnd)', 'KLTB 20N', 'Điểm kỹ thuật (*)', 'Xu hướng SMG ngắn hạn', 'Vốn hóa (tỷ đồng)', 'P/E (lần)', 'GTGD (tỷ đồng)']
df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['GTGD (tỷ đồng)'], ascending=False)
sheet.clear()
sheet.update([df.columns.values.tolist()] + df.values.tolist())
