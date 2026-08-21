import pandas as pd
import gspread
import json
import os
from google.oauth2.service_account import Credentials
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
import time
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

OUTPUT_FILE = "market_data.xlsx"
EXCHANGES = ["HOSE", "HNX", "UPCOM"]

# ── Google Sheet ──────────────────────────────────────────
def get_gsheet_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def push_to_gsheet(all_data: dict):
    """all_data = {"HOSE": df, "HNX": df, "UPCOM": df}"""
    client = get_gsheet_client()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    wb = client.open_by_key(spreadsheet_id)

    for exchange, df in all_data.items():
        # Tạo sheet nếu chưa có, dùng lại nếu đã có
        try:
            ws = wb.worksheet(exchange)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = wb.add_worksheet(title=exchange, rows=2000, cols=10)

        if df.empty:
            continue

        # Ghi header + data
        ws.update([df.columns.tolist()] + df.values.tolist())

        # Format header (bold, nền xanh đậm)
        ws.format("A1:I1", {
            "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER"
        })
        print(f"  ✅ Đã đẩy {len(df)} dòng lên sheet '{exchange}'")

    # Sheet Tổng Hợp
    try:
        ws_all = wb.worksheet("Tổng Hợp")
        ws_all.clear()
    except gspread.WorksheetNotFound:
        ws_all = wb.add_worksheet(title="Tổng Hợp", rows=5000, cols=10)

    frames = []
    for exchange, df in all_data.items():
        if not df.empty:
            df_copy = df.copy()
            df_copy.insert(0, "Sàn", exchange)
            frames.append(df_copy)

    if frames:
        df_total = pd.concat(frames, ignore_index=True)
        ws_all.update([df_total.columns.tolist()] + df_total.values.tolist())
        ws_all.format("A1:J1", {
            "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER"
        })
        print(f"  ✅ Sheet Tổng Hợp: {len(df_total)} dòng")

# ── Logic chính (giữ nguyên từ bước trước) ───────────────
def get_tickers_by_exchange():
    df = listing_companies()
    if df is None or df.empty:
        return {}
    df.columns = [c.lower().strip() for c in df.columns]
    result = {}
    for ex in EXCHANGES:
        col = next((c for c in ['exchange','comgroupcode','group_code'] if c in df.columns), None)
        subset = df[df[col].str.upper() == ex]['ticker'].tolist() if col else df['ticker'].tolist()
        result[ex] = subset
        print(f"  {ex}: {len(subset)} mã")
    return result

def fetch_latest_price(ticker, start_date, end_date):
    try:
        df = stock_historical_data(ticker=ticker, start_date=start_date,
                                   end_date=end_date, resolution='1D', type='stock')
        if df is None or df.empty:
            return None
        df.columns = [str(c).lower().strip() for c in df.columns]
        row = df.iloc[-1]
        close = row['close']
        open_ = row.get('open', close)
        high  = row.get('high', close)
        low   = row.get('low',  close)
        if close < 1000:
            close *= 1000; open_ *= 1000; high *= 1000; low *= 1000
        pct = round((close - open_) / open_ * 100, 2) if open_ else 0
        return {"Mã CK": ticker, "Ngày": str(row['time']),
                "Mở Cửa": int(open_), "Cao Nhất": int(high),
                "Thấp Nhất": int(low), "Đóng Cửa": int(close),
                "Khối Lượng": int(row['volume']), "% Thay Đổi": pct}
    except Exception:
        return None

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    print(f"📅 Export ngày: {today}")

    exchange_map = get_tickers_by_exchange()
    all_data = {}

    for exchange, tickers in exchange_map.items():
        print(f"\n🔄 {exchange} ({len(tickers)} mã)...")
        rows = [fetch_latest_price(t, start, today) for t in tickers
                if (time.sleep(0.3) or True)]
        rows = [r for r in rows if r]
        all_data[exchange] = pd.DataFrame(rows) if rows else pd.DataFrame()
        print(f"  ✅ {len(rows)} mã")

    # Export xlsx
    # ... (giữ nguyên phần openpyxl bên trên)

    # Push lên Google Sheet
    print("\n📤 Đẩy lên Google Sheet...")
    push_to_gsheet(all_data)
    print("🎉 Hoàn thành!")

if __name__ == "__main__":
    main()
