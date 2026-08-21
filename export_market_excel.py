import pandas as pd
import gspread
import json
import os
from google.oauth2.service_account import Credentials
from vnstock import Vnstock                          # ✅ v4
from datetime import datetime, timedelta
import time
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

OUTPUT_FILE = "market_data.xlsx"
EXCHANGES = ["HOSE", "HNX", "UPCOM"]

# ─────────────────────────────────────────────────────────
# GOOGLE SHEET
# ─────────────────────────────────────────────────────────
def get_gsheet_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.Client(auth=creds)

def push_to_gsheet(all_data: dict):
    client = get_gsheet_client()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    wb = client.open_by_key(spreadsheet_id)

    HEADER_FMT = {
        "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
        "textFormat": {
            "bold": True,
            "foregroundColor": {"red": 1, "green": 1, "blue": 1}
        },
        "horizontalAlignment": "CENTER"
    }

    for exchange, df in all_data.items():
        try:
            ws = wb.worksheet(exchange)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = wb.add_worksheet(title=exchange, rows=2000, cols=10)

        if df.empty:
            print(f"  ⚠️ {exchange}: không có dữ liệu")
            continue

        data = [df.columns.tolist()] + df.values.tolist()
        ws.update(data, value_input_option="RAW")
        ws.format(f"A1:{get_column_letter(len(df.columns))}1", HEADER_FMT)
        print(f"  ✅ Sheet '{exchange}': {len(df)} dòng")

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
        data_all = [df_total.columns.tolist()] + df_total.values.tolist()
        ws_all.update(data_all, value_input_option="RAW")
        ws_all.format(f"A1:{get_column_letter(len(df_total.columns))}1", HEADER_FMT)
        print(f"  ✅ Sheet 'Tổng Hợp': {len(df_total)} dòng")

# ─────────────────────────────────────────────────────────
# EXCEL (.xlsx)
# ─────────────────────────────────────────────────────────
COL_WIDTHS = [10, 14, 14, 14, 14, 14, 16, 14]

def style_sheet(ws, nrows, ncols):
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF", name="Arial", size=11)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    fill_even = PatternFill("solid", fgColor="DEEAF1")
    for row_idx in range(2, nrows + 2):
        for cell in ws[row_idx]:
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(horizontal="right")
            if row_idx % 2 == 0:
                cell.fill = fill_even
        ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")

        pct_cell = ws.cell(row=row_idx, column=ncols)
        try:
            val = float(pct_cell.value)
            pct_cell.font = Font(
                name="Arial", size=10, bold=True,
                color="00B050" if val >= 0 else "FF0000"
            )
        except (TypeError, ValueError):
            pass

    for i, w in enumerate(COL_WIDTHS[:ncols], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

def export_xlsx(all_data: dict):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Sheet Tổng Hợp đầu tiên
    frames = []
    for exchange, df in all_data.items():
        if not df.empty:
            df_copy = df.copy()
            df_copy.insert(0, "Sàn", exchange)
            frames.append(df_copy)

    if frames:
        df_total = pd.concat(frames, ignore_index=True)
        ws_all = wb.create_sheet("Tổng Hợp", 0)
        ws_all.append(df_total.columns.tolist())
        for _, r in df_total.iterrows():
            ws_all.append(r.tolist())
        style_sheet(ws_all, len(df_total), len(df_total.columns))

    # Sheet từng sàn
    for exchange, df in all_data.items():
        ws = wb.create_sheet(exchange)
        if df.empty:
            ws.append(["Không có dữ liệu"])
            continue
        ws.append(df.columns.tolist())
        for _, r in df.iterrows():
            ws.append(r.tolist())
        style_sheet(ws, len(df), len(df.columns))

    wb.save(OUTPUT_FILE)
    print(f"  ✅ Đã lưu {OUTPUT_FILE}")

# ─────────────────────────────────────────────────────────
# LẤY DỮ LIỆU
# ─────────────────────────────────────────────────────────
def get_tickers_by_exchange():
    stock = Vnstock().stock(symbol='ACB', source='VCI')
    result = {}
    for ex in EXCHANGES:
        try:
            df = stock.listing.symbols_by_exchange(exchange=ex)
            if isinstance(df, list):
                tickers = df
            else:
                df.columns = [c.lower().strip() for c in df.columns]
                col = next((c for c in ['ticker', 'symbol', 'code'] if c in df.columns), None)
                tickers = df[col].tolist() if col else []
            result[ex] = tickers
            print(f"  {ex}: {len(tickers)} mã")
        except Exception as e:
            print(f"  ⚠️ {ex}: lỗi — {e}")
            result[ex] = []
    return result

def fetch_latest_price(ticker, start_date, end_date):
    try:
        stock = Vnstock().stock(symbol=ticker, source='VCI')
        df = stock.quote.history(start=start_date, end=end_date, interval='1D')
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

        return {
            "Mã CK"      : ticker,
            "Ngày"       : str(row.get('time', row.get('date', ''))),
            "Mở Cửa"     : int(open_),
            "Cao Nhất"   : int(high),
            "Thấp Nhất"  : int(low),
            "Đóng Cửa"   : int(close),
            "Khối Lượng" : int(row['volume']),
            "% Thay Đổi" : pct,
        }
    except Exception:
        return None

# ─────────────────────────────────────────────────────────
# MAIN                                                    # ✅ đã thêm lại
# ─────────────────────────────────────────────────────────
def main():
    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    print(f"📅 Export ngày: {today}\n")

    print("📋 Lấy danh sách mã theo sàn...")
    exchange_map = get_tickers_by_exchange()

    all_data = {}
    for exchange, tickers in exchange_map.items():
        print(f"\n🔄 {exchange} ({len(tickers)} mã)...")
        rows = []
        for ticker in tickers:
            result = fetch_latest_price(ticker, start, today)
            if result:
                rows.append(result)
            time.sleep(0.3)
        all_data[exchange] = pd.DataFrame(rows) if rows else pd.DataFrame()
        print(f"  ✅ {len(rows)} mã có dữ liệu")

    print("\n📁 Xuất file Excel...")
    export_xlsx(all_data)

    print("\n📤 Đẩy lên Google Sheet...")
    push_to_gsheet(all_data)

    print("\n🎉 Hoàn thành!")

if __name__ == "__main__":
    main()
