# FORCE UPDATE - VERSION 9.2: THUẦN YFINANCE + HẠ NGƯỠNG LỌC 5 TỶ
import os
import json
import time
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
# ID FILE GOOGLE SHEET CỦA BẠN 
sheet_id = '1glhyGPKRsBwU0OXHB4gvr0dnntWn_dcw2VzI3_Z1fQc' 
sheet = client.open_by_key(sheet_id).sheet1

# 2. SIÊU CƠ SỞ DỮ LIỆU OFFLINE 350+ MÃ
print("Đang nạp Siêu danh sách 350+ mã chứng khoán 3 sàn...")

hose_symbols = ['SSI','VHM','VIC','HPG','VNM','VCB','BID','CTG','TCB','VPB','MBB','STB','ACB','SHB','VIB','HDB','LPB','TPB','MSB','OCB','SSB','EIB','NAB','NVL','PDR','DIG','DXG','NLG','KDH','KBC','VGC','SZC','HDG','BCG','FCN','CTD','VND','VCI','HCM','VIX','FTS','BSI','CTS','AGR','ORS','VDS','TVS','HSG','NKG','SMC','TLH','DGC','DPM','DCM','CSV','PHR','GVR','DPR','TRC','GMD','HAH','VOS','VHC','ANV','IDI','FMC','DBC','BAF','HAG','PAN','SBT','FRT','DGW','PET','MWG','PNJ','MSN','SAB','VJC','HVN','FPT','PLX','GAS','POW','NT2','GEG','REE','PC1','ASM','CII','HBC','VCG','HHV','LCG','HDC','IJC','SCR','CRE','KHG','DXS','PTB','GIL','TCM','TNG','VSH','SJD','SBA','TDM','BWE','VPD','VPI','QCG','TCH','HHS','HAX','CMX','DAT','EVF','FIT','HQC','ITA','OGC','HNG','TTF','AAA','APH','NHH','BMP','NTP','DRC','CSM','SRC','VTO','VIP','PVT']
hnx_symbols = ['SHS','MBS','IDC','PVS','CEO','HUT','L14','BVS','VGS','TIG','TAR','THD','BAB','NVB','PVC','PVB','APS','IDJ','API','AAV','AMV','VC3','VC7','MST','CSC','DDG','DTD','MCO','MBG','NTH','SDA','LIG','TTH','VIG','HDA','SCI','SRA','TVC','GKM']
upcom_symbols = ['BSR','ACV','VEA','MCH','VGI','FOX','VTP','OIL','ABB','BVB','VBB','SGB','PGB','KLB','SBS','AAS','VFS','C4G','G36','DDV','PAS','QNS','LTG','MSR','HTM','VGT','VNZ','SGP','PHP','TCI','DSC','BOT','DRI','TDS','HND','QTP','UPC','XDC','HSV']

exchange_map = {}
for s in hose_symbols: exchange_map[s] = 'HOSE'
for s in hnx_symbols: exchange_map[s] = 'HNX'
for s in upcom_symbols: exchange_map[s] = 'UPCOM'

symbols = list(exchange_map.keys())

# KIM BÀI MIỄN TỬ 
vip_symbols = ['VGI', 'ACV', 'VEA', 'MCH', 'BSR', 'FOX', 'VTP', 'IDC', 'PVS', 'SHS', 'MBS']

# 3. QUÉT DỮ LIỆU THUẦN TÚY BẰNG YFINANCE
data_rows = []
print(f"Bắt đầu quét {len(symbols)} mã bằng YFINANCE...")

for sym in symbols:
    try:
        exchange = exchange_map.get(sym, 'HOSE')
        
        # Tự động đổi đuôi mã cho đúng chuẩn Yahoo
        if exchange == 'HNX':
            y_sym = f"{sym}.HN"
        else:
            y_sym = f"{sym}.VN"
            
        ticker = yf.Ticker(y_sym)
        df_hist = ticker.history(period="2mo")
        
        # Nếu UPCoM tìm .VN không ra, tự động lật sang tìm đuôi .HN
        if df_hist.empty and exchange == 'UPCOM':
            y_sym = f"{sym}.HN"
            ticker = yf.Ticker(y_sym)
            df_hist = ticker.history(period="2mo")

        if df_hist.empty or len(df_hist) < 10:
            continue

        df_hist = df_hist.tail(20) 
        close_price_vnd = df_hist['Close'].iloc[-1]
        close_kvnd = close_price_vnd / 1000
        avg_vol_20 = df_hist['Volume'].mean()
        gtgd = (close_price_vnd * avg_vol_20) / 1000000000
        
        # --- BỘ LỌC THANH KHOẢN ĐÃ HẠ XUỐNG 5 TỶ ---
        if gtgd <= 5 and sym not in vip_symbols:
            continue

        ma20 = df_hist['Close'].mean()
        if close_price_vnd > ma20 * 1.01:
            trend, tech_score = "KHẢ QUAN", 5
        elif close_price_vnd < ma20 * 0.99:
            trend, tech_score = "TIÊU CỰC", 1
        else:
            trend, tech_score = "TRUNG TÍNH", 3

        try:
            info = ticker.info
            market_cap_raw = info.get('marketCap', 0)
            market_cap = (market_cap_raw / 1000000000) if market_cap_raw else "N/A"
            pe = info.get('trailingPE', "N/A")
        except Exception:
            market_cap, pe = "N/A", "N/A"

        data_rows.append([
            sym, exchange, round(close_kvnd, 2), int(avg_vol_20), tech_score, trend,
            round(market_cap, 0) if isinstance(market_cap, float) else market_cap,
            round(pe, 1) if isinstance(pe, float) else pe, round(gtgd,
