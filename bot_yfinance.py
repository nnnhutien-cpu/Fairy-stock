# FORCE UPDATE - VERSION 6.0: AI SCORING + TCBS API (CHỐNG CHẶN TUYỆT ĐỐI)
import os
import json
import requests
import time
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)
# ID FILE GOOGLE SHEET CỦA BẠN
sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. HÀM TÍNH RSI
def compute_rsi(data, window=14):
    delta = data.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

# 3. LẤY DANH SÁCH MÃ & SÀN
print("Đang tải danh sách ~1600 mã chứng khoán từ VNDirect...")
exchange_map = {}
try:
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock&size=3000"
    res = requests.get(url, headers=headers, timeout=10)
    for item in res.json().get('data', []):
        if len(item['symbol']) == 3:
            floor = item.get('floor', 'HOSE').upper()
            exchange_map[item['symbol']] = 'HOSE' if floor in ['HSX', 'VNX'] else floor
except Exception:
    print("Dùng danh sách dự phòng...")
    fallback_symbols = ['SSI','VHM','VIC','HPG','VNM','VCB','BID','CTG','TCB','VPB','MBB','STB','ACB','SHB','VIB','HDB','LPB','TPB','MSB','OCB','NVL','PDR','DIG','DXG','VND','VCI','HCM','VIX','SHS','MBS','IDC','PVS','BSR','ACV','VEA','MCH','VGI']
    for s in fallback_symbols: exchange_map[s] = 'HOSE'

symbols = list(exchange_map.keys())
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 4. HÀM XỬ LÝ TỪNG MÃ QUA TCBS API (SẠCH BÓNG LỖI YAHOO)
end_time = int(time.time())
start_time = end_time - (90 * 24 * 3600) # Lấy 90 ngày để tính RSI cho mượt

def process_ticker(sym):
    try:
        exchange = exchange_map.get(sym, 'HOSE')
        
        # TCBS Không bao giờ chặn GitHub, lấy dữ liệu 3 sàn cực chuẩn
        url_hist = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?ticker={sym}&type=stock&resolution=D&from={start_time}&to={end_time}"
        res_hist = requests.get(url_hist, timeout=5)
        hist_data = res_hist.json().get('data', [])
        
        if len(hist_data) < 30: 
            return None
            
        df = pd.DataFrame(hist_data)
        df['RSI'] = compute_rsi(df['close'], 14)
        df = df.tail(20)
        
        close_price = float(df['close'].iloc[-1])
        close_kvnd = close_price / 1000
        avg_vol_20 = float(df['volume'].mean())
        last_vol = float(df['volume'].iloc[-1])
        gtgd = (close_price * avg_vol_20) / 1000000000
        rsi_current = float(df['RSI'].iloc[-1])
        
        if gtgd <= 20 and sym not in vip_symbols:
            return None

        ma20 = float(df['close'].mean())
        
        # CHẤM ĐIỂM AI (0 - 100)
        score = 0
        # Điểm Xu Hướng
        if close_price > ma20 * 1.02: score += 40
        elif close_price > ma20: score += 25
        else: score += 10
        
        # Điểm RSI
        if 50 <= rsi_current <= 65: score += 30 
        elif 65 < rsi_current <= 75: score += 20 
        elif 40 <= rsi_current < 50: score += 15 
        else: score += 5 

        # Điểm Đột biến Khối lượng
        if last_vol > avg_vol_20 * 1.5: score += 30 
        elif last_vol > avg_vol_20 * 1.1: score += 20
        else: score += 10

        if score >= 75: trend = "TÍCH CỰC"
        elif score >= 50: trend = "TRUNG TÍNH"
        else: trend = "TIÊU CỰC"

        # Vốn hóa & P/E
        try:
            url_ov = f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/overview"
            res_ov = requests.get(url_ov, timeout=3).json()
            mcap = round(res_ov.get('marketCap', 0), 0) if res_ov.get('marketCap') else "N/A"
            pe = round(res_ov.get('pe', 0), 1) if res_ov.get('pe') else "N/A"
        except:
            mcap, pe = "N/A", "N/A"

        return [sym, exchange, round(close_kvnd, 2), int(avg_vol_20), round(rsi_current, 1), score, trend, mcap, pe, round(gtgd, 1)]
    except Exception:
        return None

# 5. ÉP CHẠY ĐA LUỒNG TỐC ĐỘ CAO
data_rows = []
print(f"Bắt đầu quét {len(symbols)} mã bằng TCBS API Đa luồng...")
# TCBS rất khỏe, ta tự tin dùng 10 công nhân chạy cùng lúc
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(process_ticker, sym): sym for sym in symbols}
    for future in as_completed(futures):
        res = future.result()
        if res: data_rows.append(res)

# 6. ĐẨY LÊN SHEET
columns = ['Mã', 'Sàn', 'Đóng cửa (k)', 'KLTB 20N', 'RSI (14)', 'Điểm AI (100)', 'Xu hướng', 'Vốn hóa (tỷ)', 'P/E', 'GTGD (tỷ)']
if data_rows:
    df = pd.DataFrame(data_rows, columns=columns).sort_values(by=['Điểm AI (100)', 'GTGD (tỷ)'], ascending=[False, False])
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"THÀNH CÔNG: Đã đẩy {len(data_rows)} mã lên Sheet!")
else:
    print("CẢNH BÁO: Không có dữ liệu!")
