# bot_reports.py
# Chạy bởi GitHub Actions (xem .github/workflows/scrape_reports.yml)
# Cào báo cáo phân tích từ DNSE + Vietstock + CafeF
# Lưu kết quả vào reports.json trong repo → app đọc qua GitHub raw URL
# ================================================================

import requests
import json
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Charset": "utf-8",
}

TODAY       = datetime.now().strftime("%Y-%m-%d")
FROM_DATE   = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")


# ── NGUỒN 1: DNSE ──────────────────────────────────────────────────────────
def fetch_dnse() -> list:
    rows = []
    try:
        resp = requests.get(
            "https://finfo-api.dnse.com.vn/v3/analyst-recommendations",
            params={"size": 200, "page": 1},
            headers=HEADERS,
            timeout=15,
        )
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            print(f"[DNSE] HTTP {resp.status_code}")
            return rows
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        for item in items:
            rows.append({
                "date":         (item.get("publishDate") or item.get("date", ""))[:10],
                "ticker":       item.get("symbol") or item.get("ticker", ""),
                "company":      item.get("firm") or item.get("company") or item.get("analyst", ""),
                "action":       item.get("recommendation") or item.get("action", ""),
                "buy_price":    item.get("currentPrice") or item.get("closePrice") or 0,
                "target_price": item.get("targetPrice") or item.get("target_price") or 0,
                "report_url":   item.get("reportUrl") or item.get("url", ""),
                "source":       "DNSE",
            })
        print(f"[DNSE] ✅ {len(rows)} báo cáo")
    except Exception as e:
        print(f"[DNSE] ❌ {e}")
    return rows


# ── NGUỒN 2: Vietstock Finance ─────────────────────────────────────────────
def fetch_vietstock() -> list:
    rows = []
    try:
        resp = requests.get(
            "https://finance.vietstock.vn/data/analyst-report",
            params={
                "fromDate": FROM_DATE,
                "toDate":   TODAY,
                "page":     1,
                "pageSize": 200,
                "catID":    0,
                "stockCode": "",
            },
            headers={**HEADERS, "Referer": "https://finance.vietstock.vn/bao-cao-phan-tich.htm"},
            timeout=15,
        )
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            print(f"[Vietstock] HTTP {resp.status_code}")
            return rows
        payload = resp.json()
        items = payload if isinstance(payload, list) else payload.get("data", payload.get("Data", []))
        for item in items:
            rows.append({
                "date":         (item.get("PublishDate") or item.get("publishDate", ""))[:10],
                "ticker":       item.get("StockCode") or item.get("stockCode") or item.get("Symbol", ""),
                "company":      item.get("AnalystFirmName") or item.get("Source") or item.get("source", ""),
                "action":       item.get("Recommendation") or item.get("recommendation") or item.get("Action", ""),
                "buy_price":    item.get("CurrentPrice") or item.get("closePrice") or 0,
                "target_price": item.get("TargetPrice") or item.get("targetPrice") or 0,
                "report_url":   item.get("ReportUrl") or item.get("reportUrl") or item.get("DocumentUrl", ""),
                "source":       "Vietstock",
            })
        print(f"[Vietstock] ✅ {len(rows)} báo cáo")
    except Exception as e:
        print(f"[Vietstock] ❌ {e}")
    return rows


# ── NGUỒN 3: CafeF ─────────────────────────────────────────────────────────
def fetch_cafef() -> list:
    rows = []
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(
            "https://cafef.vn/thi-truong-chung-khoan/khuyen-nghi-dau-tu.chn",
            headers=HEADERS,
            timeout=15,
        )
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"class": lambda c: c and "tbl" in c.lower()})
        if not table:
            print("[CafeF] Không tìm thấy bảng dữ liệu")
            return rows
        for tr in table.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) < 4:
                continue
            link_tag = tr.find("a", href=True)
            link = ("https://cafef.vn" + link_tag["href"]) if link_tag else ""
            rows.append({
                "date":         tds[0] if len(tds) > 0 else "",
                "ticker":       tds[1] if len(tds) > 1 else "",
                "company":      tds[2] if len(tds) > 2 else "",
                "action":       tds[3] if len(tds) > 3 else "",
                "buy_price":    tds[4] if len(tds) > 4 else 0,
                "target_price": tds[5] if len(tds) > 5 else 0,
                "report_url":   link,
                "source":       "CafeF",
            })
        print(f"[CafeF] ✅ {len(rows)} báo cáo")
    except Exception as e:
        print(f"[CafeF] ❌ {e}")
    return rows


# ── NGUỒN 4: DNSE endpoint khác (research notes) ───────────────────────────
def fetch_dnse_research() -> list:
    rows = []
    try:
        resp = requests.get(
            "https://finfo-api.dnse.com.vn/v2/research-reports",
            params={"size": 100, "page": 1, "fromDate": FROM_DATE, "toDate": TODAY},
            headers=HEADERS,
            timeout=15,
        )
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return rows
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
        for item in items:
            rows.append({
                "date":         (item.get("publishDate") or item.get("date", ""))[:10],
                "ticker":       item.get("symbol") or item.get("stockCode", ""),
                "company":      item.get("source") or item.get("firm", "DNSE Research"),
                "action":       item.get("recommendation") or item.get("type", ""),
                "buy_price":    item.get("currentPrice") or 0,
                "target_price": item.get("targetPrice") or 0,
                "report_url":   item.get("url") or item.get("reportUrl", ""),
                "source":       "DNSE Research",
            })
        print(f"[DNSE Research] ✅ {len(rows)} báo cáo")
    except Exception as e:
        print(f"[DNSE Research] ❌ {e}")
    return rows


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    print(f"=== Bắt đầu cào dữ liệu báo cáo: {TODAY} ===")

    all_rows = []
    fetchers = [fetch_dnse, fetch_vietstock, fetch_cafef, fetch_dnse_research]

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fn): fn.__name__ for fn in fetchers}
        for future in as_completed(futures, timeout=30):
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as e:
                print(f"Thread error: {e}")

    # Dedup theo date + ticker + company
    seen = set()
    deduped = []
    for row in all_rows:
        key = (row.get("date", ""), row.get("ticker", ""), row.get("company", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    # Sắp xếp mới nhất trước
    deduped.sort(key=lambda x: x.get("date", ""), reverse=True)

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total":      len(deduped),
        "data":       deduped,
    }

    out_path = os.path.join(os.path.dirname(__file__), "reports.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"=== Xong: {len(deduped)} báo cáo → reports.json ===")


if __name__ == "__main__":
    main()
