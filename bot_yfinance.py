# FORCE UPDATE - VERSION 13.0: VNSTOCK API 4.0.1 (NEW ARCHITECTURE)
import os
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- SỬ DỤNG KIẾN TRÚC MỚI NHẤT CỦA VNSTOCK 4.0.1 ---
from vnstock.api.quote import Quote
from vnstock.api.company import Company

# 1. KẾT NỐI GOOGLE SHEETS
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    raise ValueError("LỖI: Không tìm thấy GCP_CREDENTIALS!")
creds_dict = json.loads(creds_json)
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)

sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. HÀM TÍNH TOÁN RSI
def compute_rsi(series, window=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# 3. SIÊU CƠ SỞ DỮ LIỆU OFFLINE 350+ MÃ
print("Đang nạp Siêu danh sách mã chứng khoán 3 sàn...")

hose_symbols = ['SSI','VHM','VIC','HPG','VNM','VCB','BID','CTG','TCB','VPB','MBB','STB','ACB','SHB','VIB','HDB','LPB','TPB','MSB','OCB','SSB','EIB','NAB','NVL','PDR','DIG','DXG','NLG','KDH','KBC','VGC','SZC','HDG','BCG','FCN','CTD','VND','VCI','HCM','VIX','FTS','BSI','CTS','AGR','ORS','VDS','TVS','HSG','NKG','SMC','TLH','DGC','DPM','DCM','CSV','PHR','GVR','DPR','TRC','GMD','HAH','VOS','VHC','ANV','IDI','FMC','DBC','BAF','HAG','PAN','SBT','FRT','DGW','PET','MWG','PNJ','MSN','SAB','VJC','HVN','FPT','PLX','GAS','POW','NT2','GEG','REE','PC1','ASM','CII','HBC','VCG','HHV','LCG','HDC','IJC','SCR','CRE','KHG','DXS','PTB','GIL','TCM','TNG','VSH','SJD','SBA','TDM','BWE','VPD','VPI','QCG','TCH','HHS','HAX','CMX','DAT','EVF','FIT','HQC','ITA','OGC','HNG','TTF','AAA','APH','NHH','BMP','NTP','DRC','CSM','SRC','VTO','VIP','PVT']
hnx_symbols = ['SHS','MBS','IDC','PVS','CEO','HUT','L14','BVS','VGS','TIG','TAR','THD','BAB','NVB','PVC','PVB','APS','IDJ','API','AAV','AMV','VC3','VC7','MST','CSC','DDG','DTD','MCO','MBG','NTH','SDA','LIG','TTH','VIG','HDA','SCI','SRA','TVC','GKM']
upcom_symbols = ['BSR','ACV','VEA','MCH','VGI','FOX','VTP','OIL','ABB','BVB','VBB','SGB','PGB','KLB','SBS','AAS','VFS','C4G','G36','DDV','PAS','QNS','LTG','MSR','HTM','VGT','VNZ','SGP','PHP','TCI','DSC','BOT','DRI','TDS','HND','QTP','UPC','XDC','HSV']

exchange_map = {}
for s in hose_symbols: exchange_map[s] = 'HOSE'
for s in hnx_symbols: exchange_map[s] = 'HNX'
for s in upcom_symbols: exchange_map[s] = 'UPCOM'

symbols = list(exchange_map.keys())
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 4. QUÉT DỮ LIỆU BẰNG KIẾN TRÚC MỚI VÀ LÁCH TƯỜNG LỬA
data_rows = []
print(f"Bắt đầu quét {len(symbols)} mã bằng VNSTOCK 4.0.1 (Sẽ mất khoảng 10-12 phút để lách Rate Limit)...")

end_date = datetime.now().strftime('%Y-%m-%d')
start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

for idx, sym in enumerate(symbols):
    try:
        exchange = exchange_map.get(sym, 'HOSE')
        
        # --- Cú pháp MỚI: Dùng Quote thay cho Vnstock().stock ---
        q = Quote(symbol=sym, source='VCI')
        df = q.history(start=start_date, end=end_date)
        
        if df is None or df.empty or len(df) < 30:
            time.sleep(3.1) # Vẫn giữ nhịp nghỉ 3.1s để không bị khóa API
            continue
            
        col_close = 'close' if 'close' in df.columns else 'Close'
        col_vol = 'volume' if 'volume' in df.columns else 'Volume'

        df['RSI'] = compute_rsi(df[col_close], 14)
        df = df.tail(20)
        
        close_price = float(df[col_close].iloc[-1])
        if close_price > 1000:
            close_price_vnd = close_price
            close_kvnd = close_price / 1000
        else:
            close_price_vnd = close_price * 1000
            close_kvnd = close_price

        avg_vol_20 = float(df[col_vol].mean())
        last_vol = float(df[col_vol].iloc[-1])
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        rsi_current = float(df['RSI'].iloc[-1])
        
        # Bộ lọc thanh khoản
        if gtgd <= 20 and sym not in vip_symbols:
            time.sleep(3.1) 
            continue

        ma20 = float(df[col_close].mean())
        
        # Chấm điểm AI
        score = 0
        if close_price > ma20 * 1.02: score += 40
        elif close_price > ma20: score += 25
        else: score += 10
        
        if 50 <= rsi_current <= 65: score += 30  
        elif 65 < rsi_current <= 75: score += 20 
        elif 40 <= rsi_current < 50: score += 15 
        else: score += 5                         

        if last_vol > avg_vol_20 * 1.5: score += 30 
        elif last_vol > avg_vol_20 * 1.1: score += 20
        else: score += 10

        if score >= 75: trend = "TÍCH CỰC"
        elif score >= 50: trend = "TRUNG TÍNH"
        else: trend = "TIÊU CỰC"

        # --- Lấy Vốn hóa, P/E bằng Company API mới (Dùng VCI thay vì TCBS bị cấm) ---
        try:
            comp = Company(symbol=sym, source='VCI')
            overview = comp.overview()
            
            if overview is not None and not overview.empty:
                col_mcap = 'marketcap' if 'marketcap' in overview.columns else ('marketCap' if 'marketCap' in overview.columns else None)
                col_pe = 'pe' if 'pe' in overview.columns else ('PE' if 'PE' in overview.columns else None)
                
                mcap = round(float(overview[col_mcap].iloc[0]) / 1000, 0) if col_mcap else "N/A"
                pe = round(float(overview[col_pe].iloc[0]), 1) if col_pe else "N/A"
            else:
                mcap, pe = "N/A", "N/A"
        except:
            mcap, pe = "N/A", "N/A"

        data_rows.append([
            sym, exchange, round(close_kvnd, 2), int(avg_vol_20), 
            round(rsi_current, 1), score, trend, mcap, pe, round(gtgd, 1)
        ])
        
        # Nghỉ chuẩn 3.1 giây để vượt tường lửa Rate Limit
        time.sleep(3.1) 
        if (idx+1) % 10 == 0:
            print(f" Đã xử lý {idx+1}/{len(symbols)} mã...")
            
    except Exception as e:
        time.sleep(3.1)
        continue

# 5. ĐỒNG BỘ DỮ LIỆU LÊN GOOGLE SHEET
columns = ['Mã', 'Sàn', 'Đóng cửa (k)', 'KLTB 20N', 'RSI (14)', 'Điểm AI (100)', 'Xu hướng', 'Vốn hóa (tỷ)', 'P/E', 'GTGD (tỷ)']
if data_rows:
    df_result = pd.DataFrame(data_rows, columns=columns).sort_values(by=['Điểm AI (100)', 'GTGD (tỷ)'], ascending=[False, False])
    sheet.clear()
    sheet.update([df_result.columns.values.tolist()] + df_result.values.tolist())
    print(f" THÀNH CÔNG: Đã quét và đẩy {len(data_rows)} mã toàn thị trường lên Sheet!")
else:
    print(" CẢNH BÁO: Không lấy được dữ liệu thô. Có thể do Rate Limit mạng.")
