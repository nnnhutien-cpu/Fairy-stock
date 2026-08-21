import pandas as pd
from vnstock import listing_companies, stock_historical_data
from datetime import datetime, timedelta
import time
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

OUTPUT_FILE = "market_data.xlsx"

# 3 sàn: HOSE, HNX, UPCOM
EXCHANGES = ["HOSE", "HNX", "UPCOM"]

def get_tickers_by_exchange():
    """Lấy danh sách mã theo từng sàn"""
    df = listing_companies()
    if df is None or df.empty:
        return {}
    
    # Chuẩn hóa tên cột
    df.columns = [c.lower().strip() for c in df.columns]
    
    result = {}
    for ex in EXCHANGES:
        col = None
        # listing_companies thường có cột 'exchange' hoặc 'comGroupCode'
        for candidate in ['exchange', 'comgroupcode', 'group_code']:
            if candidate in df.columns:
                col = candidate
                break
        
        if col:
            subset = df[df[col].str.upper() == ex]['ticker'].tolist()
        else:
            # Fallback: dùng hết nếu không phân biệt được sàn
            subset = df['ticker'].tolist()
        
        result[ex] = subset
        print(f"  {ex}: {len(subset)} mã")
    
    return result

def fetch_latest_price(ticker, start_date, end_date):
    """Lấy giá đóng cửa mới nhất của 1 mã"""
    try:
        df = stock_historical_data(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            resolution='1D',
            type='stock'
        )
        if df is None or df.empty:
            return None
        
        df.columns = [str(c).lower().strip() for c in df.columns]
        row = df.iloc[-1]

        gia_dong_cua = row['close']
        gia_mo_cua  = row.get('open',  row['close'])
        gia_cao     = row.get('high',  row['close'])
        gia_thap    = row.get('low',   row['close'])

        # vnstock đôi khi trả giá chưa nhân 1000
        if gia_dong_cua < 1000:
            for g in ['gia_dong_cua', 'gia_mo_cua', 'gia_cao', 'gia_thap']:
                locals()[g]  # touch — multiply below
            gia_dong_cua *= 1000
            gia_mo_cua   *= 1000
            gia_cao      *= 1000
            gia_thap     *= 1000

        pct = ((gia_dong_cua - gia_mo_cua) / gia_mo_cua * 100) if gia_mo_cua else 0

        return {
            "Mã CK"       : ticker,
            "Ngày"        : str(row['time']),
            "Mở Cửa"      : int(gia_mo_cua),
            "Cao Nhất"    : int(gia_cao),
            "Thấp Nhất"   : int(gia_thap),
            "Đóng Cửa"    : int(gia_dong_cua),
            "Khối Lượng"  : int(row['volume']),
            "% Thay Đổi"  : round(pct, 2),
        }
    except Exception:
        return None

def style_header(ws):
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF", name="Arial", size=11)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

def style_data_rows(ws, nrows):
    fill_even = PatternFill("solid", fgColor="DEEAF1")
    font_normal = Font(name="Arial", size=10)
    for row_idx in range(2, nrows + 2):
        for cell in ws[row_idx]:
            cell.font = font_normal
            cell.alignment = Alignment(horizontal="right")
            if row_idx % 2 == 0:
                cell.fill = fill_even
        # Mã CK căn giữa
        ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")
        # % Thay Đổi: tô màu đỏ/xanh
        pct_cell = ws.cell(row=row_idx, column=8)
        try:
            val = float(pct_cell.value)
            pct_cell.font = Font(
                name="Arial", size=10,
                color="00B050" if val >= 0 else "FF0000",
                bold=True
            )
        except Exception:
            pass

def set_col_widths(ws):
    widths = [10, 14, 14, 14, 14, 14, 16, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    print(f"📅 Export ngày: {today}")

    print("📋 Lấy danh sách mã theo sàn...")
    exchange_map = get_tickers_by_exchange()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # xóa sheet mặc định

    for exchange, tickers in exchange_map.items():
        print(f"\n🔄 Đang cào {exchange} ({len(tickers)} mã)...")
        rows = []

        for ticker in tickers:            # xóa [:50] để cào hết
            data = fetch_latest_price(ticker, start, today)
            if data:
                rows.append(data)
            time.sleep(0.3)

        # Ghi vào sheet riêng cho mỗi sàn
        ws = wb.create_sheet(title=exchange)
        if not rows:
            ws.append(["Không có dữ liệu"])
            continue

        df = pd.DataFrame(rows)
        # Header
        ws.append(df.columns.tolist())
        # Data
        for _, r in df.iterrows():
            ws.append(r.tolist())

        style_header(ws)
        style_data_rows(ws, len(rows))
        set_col_widths(ws)
        ws.freeze_panes = "A2"

        print(f"  ✅ {exchange}: {len(rows)} mã")

    # Sheet tổng hợp
    ws_all = wb.create_sheet(title="Tổng Hợp", index=0)
    all_rows = []
    for exchange, tickers in exchange_map.items():
        ws_ex = wb[exchange]
        for row in ws_ex.iter_rows(min_row=2, values_only=True):
            if row[0] and row[0] != "Không có dữ liệu":
                all_rows.append((exchange,) + row)

    if all_rows:
        headers = ["Sàn", "Mã CK", "Ngày", "Mở Cửa", "Cao Nhất",
                   "Thấp Nhất", "Đóng Cửa", "Khối Lượng", "% Thay Đổi"]
        ws_all.append(headers)
        for r in all_rows:
            ws_all.append(list(r))
        style_header(ws_all)
        style_data_rows(ws_all, len(all_rows))
        for i, w in enumerate([8, 10, 14, 14, 14, 14, 14, 16, 14], 1):
            ws_all.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
        ws_all.freeze_panes = "A2"

    wb.save(OUTPUT_FILE)
    print(f"\n🎉 Đã lưu: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
