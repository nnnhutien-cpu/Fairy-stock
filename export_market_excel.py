"""
export_market_excel.py
=======================
Lấy dữ liệu giá 6 tháng gần nhất cho toàn bộ mã cổ phiếu sàn HOSE
(dùng vnstock, cùng cách data_loader.py trong app Fairy-stock đang dùng),
rồi xuất ra 1 file Excel (.xlsx) gồm 2 sheet:
  - Summary: tổng quan mỗi mã (giá mới nhất, % thay đổi 6 tháng, KL trung bình...)
  - Price_History: dữ liệu giá theo ngày, tất cả các mã (dạng bảng dài)

Cách chạy:
    pip install -r requirements.txt
    python scripts/export_market_excel.py

Biến môi trường tuỳ chọn:
    VNSTOCK_RATE_LIMIT   số request/phút cho phép (mặc định 18, an toàn dưới mức 20/phút
                          của tài khoản khách chưa đăng ký API key)
    DAYS_BACK             số ngày lịch sử lấy (mặc định 183 ~ 6 tháng)
    EXCHANGE               HOSE | HNX | UPCOM | all (mặc định HOSE)
"""

import os
import time
import threading
from datetime import datetime, timedelta

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows

from vnstock.api.quote import Quote
from vnstock.api.listing import Listing

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
RATE_LIMIT_PER_MIN = int(os.environ.get("VNSTOCK_RATE_LIMIT", "18"))
DAYS_BACK = int(os.environ.get("DAYS_BACK", "183"))
EXCHANGE = os.environ.get("EXCHANGE", "HOSE").upper()
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "data/market_export.xlsx")
SOURCES = ["VCI", "MSN"]  # thứ tự nguồn dự phòng, giống data_loader.py

# ---------------------------------------------------------------------------
# Rate limiter (giống cơ chế trong data_loader.py: chủ động rải request,
# không để thư viện tự chặn rồi retry ngầm)
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_call_timestamps = []


def _throttle():
    with _rate_lock:
        now = time.time()
        while _call_timestamps and now - _call_timestamps[0] > 60:
            _call_timestamps.pop(0)
        if len(_call_timestamps) >= RATE_LIMIT_PER_MIN:
            wait = 60 - (now - _call_timestamps[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            while _call_timestamps and now - _call_timestamps[0] > 60:
                _call_timestamps.pop(0)
        _call_timestamps.append(time.time())


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if "date" in df.columns and "time" not in df.columns:
        df.rename(columns={"date": "time"}, inplace=True)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        if getattr(df["time"].dt, "tz", None) is not None:
            df["time"] = df["time"].dt.tz_localize(None)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "time" in df.columns:
        df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def get_all_tickers(exchange: str = "HOSE") -> list:
    """Lấy danh sách mã cổ phiếu theo sàn — cùng logic get_all_tickers() trong data_loader.py."""
    for src in ["vci", "kbs"]:
        try:
            _throttle()
            df = Listing(source=src).symbols_by_exchange()
            df.columns = [str(c).lower().strip() for c in df.columns]
            type_col = next((c for c in df.columns if "type" in c), None)
            if type_col:
                df = df[df[type_col].astype(str).str.upper().isin(["STOCK", "CP", "CỔ PHIẾU"])]
            if "exchange" in df.columns and exchange != "ALL":
                targets = ["HOSE", "HSX"] if exchange in ("HOSE", "HSX") else [exchange]
                df = df[df["exchange"].astype(str).str.upper().isin(targets)]
            col = "symbol" if "symbol" in df.columns else ("ticker" if "ticker" in df.columns else None)
            if col:
                tickers = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
                if tickers:
                    return sorted(set(tickers))
        except Exception as e:
            print(f"[WARN] Listing source '{src}' failed: {e}")
            continue
    raise RuntimeError("Không lấy được danh sách mã — kiểm tra kết nối mạng / vnstock.")


def fetch_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    for src in SOURCES:
        try:
            _throttle()
            df = Quote(symbol=symbol, source=src).history(start=start, end=end, interval="1D")
            if df is not None and not df.empty:
                return _normalize(df)
        except Exception:
            continue
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Excel styling helpers
# ---------------------------------------------------------------------------
FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF")
NORMAL = Font(name=FONT)
THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def write_df_sheet(wb: Workbook, name: str, df: pd.DataFrame, number_formats: dict | None = None):
    ws = wb.create_sheet(name)
    number_formats = number_formats or {}
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), start=1):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = HEADER_FONT
                cell.fill = HEADER_FILL
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.font = NORMAL
                col_name = df.columns[c_idx - 1]
                if col_name in number_formats:
                    cell.number_format = number_formats[col_name]
            cell.border = BORDER
    for i, col in enumerate(df.columns, start=1):
        max_len = max(len(str(col)), df[col].astype(str).map(len).max() if len(df) else 0)
        ws.column_dimensions[get_column_letter(i)].width = min(max(max_len + 2, 10), 22)
    ws.freeze_panes = "A2"
    return ws


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"[INFO] Lấy danh sách mã sàn {EXCHANGE} ...")
    tickers = get_all_tickers(EXCHANGE)
    print(f"[INFO] Tổng {len(tickers)} mã. Bắt đầu tải lịch sử {DAYS_BACK} ngày (rate limit {RATE_LIMIT_PER_MIN}/phút)...")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")

    all_rows = []
    summary_rows = []

    for i, ticker in enumerate(tickers, start=1):
        df = fetch_history(ticker, start_date, end_date)
        if df.empty:
            print(f"  [{i}/{len(tickers)}] {ticker}: KHÔNG có dữ liệu, bỏ qua")
            continue

        df["ticker"] = ticker
        all_rows.append(df[["ticker", "time", "open", "high", "low", "close", "volume"]])

        first_close = df["close"].iloc[0]
        last_close = df["close"].iloc[-1]
        pct_change = (last_close / first_close - 1) if first_close else None
        summary_rows.append(
            {
                "Mã": ticker,
                "Giá mới nhất": last_close,
                "Giá đầu kỳ": first_close,
                "% Thay đổi (kỳ)": pct_change,
                "Cao nhất": df["high"].max(),
                "Thấp nhất": df["low"].min(),
                "KL trung bình/phiên": df["volume"].mean(),
                "Số phiên có dữ liệu": len(df),
                "Ngày cập nhật cuối": df["time"].max().strftime("%Y-%m-%d"),
            }
        )
        if i % 25 == 0 or i == len(tickers):
            print(f"  [{i}/{len(tickers)}] đã xử lý...")

    if not summary_rows:
        raise RuntimeError("Không tải được dữ liệu cho bất kỳ mã nào — kiểm tra kết nối/rate limit.")

    summary_df = pd.DataFrame(summary_rows).sort_values("Mã").reset_index(drop=True)
    history_df = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    history_df = history_df.rename(
        columns={"ticker": "Mã", "time": "Ngày", "open": "Mở cửa", "high": "Cao nhất",
                 "low": "Thấp nhất", "close": "Đóng cửa", "volume": "Khối lượng"}
    )
    history_df["Ngày"] = history_df["Ngày"].dt.strftime("%Y-%m-%d")

    print(f"[INFO] Ghi ra Excel: {OUTPUT_PATH}")
    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)  # bỏ sheet mặc định trống

    write_df_sheet(
        wb,
        "Summary",
        summary_df,
        number_formats={
            "Giá mới nhất": "0.00",
            "Giá đầu kỳ": "0.00",
            "% Thay đổi (kỳ)": "0.00%",
            "Cao nhất": "0.00",
            "Thấp nhất": "0.00",
            "KL trung bình/phiên": "#,##0",
        },
    )
    write_df_sheet(
        wb,
        "Price_History",
        history_df,
        number_formats={
            "Mở cửa": "0.00",
            "Cao nhất": "0.00",
            "Thấp nhất": "0.00",
            "Đóng cửa": "0.00",
            "Khối lượng": "#,##0",
        },
    )

    wb.save(OUTPUT_PATH)
    print(f"[DONE] Đã lưu {OUTPUT_PATH} — {len(summary_df)} mã, {len(history_df)} dòng dữ liệu giá.")


if __name__ == "__main__":
    main()
