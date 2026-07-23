# market_breadth.py
"""
Sức khỏe thị trường (Market Breadth):
- Index groups: VN30, Blue, Penny
- Breadth: Advance/Decline, ROC, MA20/60, Đỉnh/Đáy
"""
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st


# ============================================================
# 1. BẢNG 1: INDEX GROUPS
# ============================================================
@st.cache_data(ttl=180, show_spinner=False)   # refresh 3 phút
def get_index_groups():
    """
    Lấy dữ liệu các nhóm chỉ số:
    - VN30, Blue (VN-BlueChip), Penny, MidCap, SmallCap
    """
    try:
        from vnstock import Trading
        indices = {
            "VN30 Index":     "VN30",
            "Blue Index":     "VNSML",
            "Penny Index":    "VNMID",
        }

        rows = []
        end   = dt.date.today().strftime("%Y-%m-%d")
        start = (dt.date.today() - dt.timedelta(days=10)).strftime("%Y-%m-%d")

        for name, code in indices.items():
            try:
                trading = Trading(source="VCI")
                df = trading.get_index_series(
                    index_code=code,
                    start_date=start,
                    end_date=end,
                )
                if df is None or df.empty:
                    rows.append(_empty_group(name))
                    continue

                df = df.sort_values("time").reset_index(drop=True)
                cur, prev = df.iloc[-1], df.iloc[-2]

                change      = float(cur["close"] - prev["close"])
                change_pct  = float((cur["close"] - prev["close"]) / prev["close"] * 100)
                value_today = float(cur.get("total_match_volume",
                                            cur.get("volume", 0))) / 1e9   # tỷ

                # Value 5 phiên trước (TB)
                if len(df) >= 6:
                    val_5d = float(df["close"].iloc[-6]) * \
                             float(df.get("total_match_volume",
                                          df.get("volume", 0)).iloc[-6]) / 1e9
                else:
                    val_5d = value_today

                value_ratio = (value_today / val_5d * 100) if val_5d > 0 else 100

                rows.append({
                    "name":         name,
                    "change_pct":   round(change_pct, 2),
                    "value_today":  round(value_today, 2),
                    "value_5d_ago": round(val_5d, 2),
                    "value_ratio":  round(value_ratio, 2),
                })
            except Exception as e:
                print(f"[index_groups] {name} failed: {e}")
                rows.append(_empty_group(name))

        return rows
    except Exception as e:
        print(f"[get_index_groups] {e}")
        return [_empty_group("VN30 Index"),
                _empty_group("Blue Index"),
                _empty_group("Penny Index")]


def _empty_group(name):
    return {"name": name, "change_pct": 0,
            "value_today": 0, "value_5d_ago": 0, "value_ratio": 100}


# ============================================================
# 2. BẢNG 2: BREADTH INDICATORS
# ============================================================
@st.cache_data(ttl=180, show_spinner=False)
def get_market_breadth():
    """
    Tính các chỉ số breadth toàn thị trường:
    - Advance/Decline (Tăng/Giảm)
    - New High/Low 1M, 3M
    - ROC5, ROC10, ROC20
    - MA20, MA60 (số mã trên/dưới)
    """
    try:
        from vnstock import Vnstock

        # Lấy danh sách mã HOSE (~400 mã)
        symbols = _get_hose_symbols()
        if not symbols:
            return _empty_breadth()

        # Lấy dữ liệu giá 60 phiên gần nhất
        prices = _fetch_prices_batch(symbols, days=60)
        if prices.empty:
            return _empty_breadth()

        result = {}

        # ---- 1. Advance / Decline ----
        adv = int((prices["change_pct"].iloc[-1] > 0).sum())
        dec = int((prices["change_pct"].iloc[-1] < 0).sum())
        flat = len(prices) - adv - dec
        result["advance"]     = adv
        result["decline"]     = dec
        result["flat"]        = flat
        result["ad_ratio"]    = round(adv / max(dec, 1), 2)
        result["ad_change"]   = prices["change_pct"].iloc[-1].mean()

        # Đánh giá tổng
        if result["ad_ratio"] > 1.5 and result["ad_change"] > 0.5:
            result["verdict"] = "🟢 TÍCH CỰC"
        elif result["ad_ratio"] < 0.7 or result["ad_change"] < -0.5:
            result["verdict"] = "🔴 TIÊU CỰC"
        else:
            result["verdict"] = "🟡 TRUNG TÍNH"

        # ---- 2. New High / Low 20 phiên (1 tháng) ----
        highs_1m = int((prices["close"].iloc[-1] >
                        prices["high"].iloc[-21:-1].max(axis=1)).sum())
        lows_1m  = int((prices["close"].iloc[-1] <
                        prices["low"].iloc[-21:-1].min(axis=1)).sum())
        result["highs_1m"] = highs_1m
        result["lows_1m"]  = lows_1m
        result["trend_1m"] = "UP" if highs_1m > lows_1m * 2 else \
                             "DOWN" if lows_1m > highs_1m * 2 else "SIDEWAY"

        # ---- 3. New High / Low 60 phiên (3 tháng) ----
        highs_3m = int((prices["close"].iloc[-1] >
                        prices["high"].iloc[:-1].max()).sum())
        lows_3m  = int((prices["close"].iloc[-1] <
                        prices["low"].iloc[:-1].min()).sum())
        result["highs_3m"] = highs_3m
        result["lows_3m"]  = lows_3m
        result["trend_3m"] = "UP" if highs_3m > lows_3m * 2 else \
                             "DOWN" if lows_3m > highs_3m * 2 else "SIDEWAY"

        # ---- 4. ROC5 / ROC10 / ROC20 ----
        for n in [5, 10, 20]:
            col_name = f"roc{n}"
            if len(prices) >= n + 1:
                up   = int((prices[col_name].iloc[-1] > 0).sum())
                down = int((prices[col_name].iloc[-1] < 0).sum())
                avg  = float(prices[col_name].iloc[-1].mean())
                result[f"roc{n}_up"]   = up
                result[f"roc{n}_down"] = down
                result[f"roc{n}_avg"]  = round(avg, 2)
                result[f"roc{n}_trend"] = "DOWN" if avg < -3 else \
                                          "UP" if avg > 3 else "SIDEWAY"

        # ---- 5. MA20 / MA60 (số mã nằm trên/dưới) ----
        for n in [20, 60]:
            col_name = f"above_ma{n}"
            if col_name in prices.columns:
                above = int(prices[col_name].iloc[-1].sum())
                below = len(prices) - above
                pct   = float(prices[col_name].iloc[-1].mean() * 100)
                result[f"ma{n}_above"]  = above
                result[f"ma{n}_below"]  = below
                result[f"ma{n}_pct"]    = round(pct, 2)
                result[f"ma{n}_trend"]  = "DOWN" if pct < 20 else \
                                          "UP" if pct > 60 else "SIDEWAY"

        return result

    except Exception as e:
        print(f"[get_market_breadth] {e}")
        return _empty_breadth()


def _get_all_symbols():
    """
    Lấy danh sách mã từ CẢ 3 SÀN: HOSE + HNX + UPCOM.
    Trả về dict: {symbol: exchange}
    """
    symbols = {}   # {symbol: exchange}

    try:
        from vnstock import Trading

        # ===== HOSE =====
        try:
            trading = Trading(source="VCI")
            hose_list = trading.symbols_by_exchange(exchange="HOSE")
            if hose_list is not None and not hose_list.empty:
                if "ticker" in hose_list.columns:
                    for sym in hose_list["ticker"].tolist():
                        symbols[str(sym).upper()] = "HOSE"
                elif "symbol" in hose_list.columns:
                    for sym in hose_list["symbol"].tolist():
                        symbols[str(sym).upper()] = "HOSE"
        except Exception as e:
            print(f"[get_symbols] HOSE failed: {e}")

        # ===== HNX =====
        try:
            trading = Trading(source="VCI")
            hnx_list = trading.symbols_by_exchange(exchange="HNX")
            if hnx_list is not None and not hnx_list.empty:
                if "ticker" in hnx_list.columns:
                    for sym in hnx_list["ticker"].tolist():
                        symbols[str(sym).upper()] = "HNX"
                elif "symbol" in hnx_list.columns:
                    for sym in hnx_list["symbol"].tolist():
                        symbols[str(sym).upper()] = "HNX"
        except Exception as e:
            print(f"[get_symbols] HNX failed: {e}")

        # ===== UPCOM =====
        try:
            trading = Trading(source="VCI")
            upc_list = trading.symbols_by_exchange(exchange="UPCOM")
            if upc_list is not None and not upc_list.empty:
                if "ticker" in upc_list.columns:
                    for sym in upc_list["ticker"].tolist():
                        symbols[str(sym).upper()] = "UPCOM"
                elif "symbol" in upc_list.columns:
                    for sym in upc_list["symbol"].tolist():
                        symbols[str(sym).upper()] = "UPCOM"
        except Exception as e:
            print(f"[get_symbols] UPCOM failed: {e}")

    except Exception as e:
        print(f"[get_all_symbols] {e}")

    # ===== Fallback nếu API lỗi: hard-code =====
    if len(symbols) < 50:
        print("[get_all_symbols] API failed, using fallback list")
        # Top 60 mã (chia đều 3 sàn)
        hose = ["VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "HDB", "SSB",
                "VIC", "VHM", "NVL", "PDR", "KDH", "VRE", "BCM",
                "HPG", "HSG", "NKG", "POM",
                "VNM", "MSN", "SAB", "KDC", "MCH",
                "MWG", "FRT", "PNJ", "DGW",
                "FPT", "CMG", "ELC",
                "GAS", "PLX", "PVS", "PVD", "BSR",
                "VJC", "HVN",
                "REE", "GMD", "HAH", "TCL",
                "SSI", "VCI", "HCM", "VND",
                "POW", "NTL", "GEX",
                "SBT", "VHC", "DPM", "DGC",
                "TPB", "SHB", "LPB", "OCB", "MSB", "EIB"]
        hnx = ["SHS", "VNR", "PGS", "PVC", "CEO", "DDG", "IDJ",
               "HUT", "LAS", "SJF", "TNG", "SHB",
               "NBC", "NVB", "VIB",
               "PSD", "PVC", "PVI", "BVS",
               "NHA", "VKC", "THD",
               "MST", "VCG", "VGS"]
        upcom = ["VEA", "BSR", "MCH", "VGT", "VIB",
                 "ACV", "CTR", "VTP", "GEG",
                 "VEF", "OIL", "PXL", "NBC",
                 "ABB", "VTB", "TCI", "BAB",
                 "SBS", "SII", "SGB"]

        for sym in hose:   symbols[sym] = "HOSE"
        for sym in hnx:    symbols[sym] = "HNX"
        for sym in upcom:  symbols[sym] = "UPCOM"

    return symbols


def _get_hose_symbols():
    """Backward compatible - chỉ trả về HOSE symbols."""
    all_syms = _get_all_symbols()
    return [s for s, ex in all_syms.items() if ex == "HOSE"][:80]


def _fetch_prices_batch(symbols, days=60):
    """Lấy giá theo batch — có tính ROC, MA20, MA60."""
    try:
        from vnstock import Vnstock
        end   = dt.date.today().strftime("%Y-%m-%d")
        start = (dt.date.today() - dt.timedelta(days=days + 30)).strftime("%Y-%m-%d")

        all_data = []
        for sym in symbols:
            try:
                stock = Vnstock().stock(symbol=sym, source="VCI")
                df = stock.quote.history(start=start, end=end, interval="1D")
                if df is None or df.empty or len(df) < 30:
                    continue
                df = df.sort_values("time").reset_index(drop=True)
                df["symbol"] = sym
                all_data.append(df)
            except Exception:
                continue

        if not all_data:
            return pd.DataFrame()

        full = pd.concat(all_data, ignore_index=True)

        # Pivot: rows=symbol, cols=time
        closes = full.pivot(index="symbol", columns="time", values="close")
        highs  = full.pivot(index="symbol", columns="time", values="high")
        lows   = full.pivot(index="symbol", columns="time", values="low")

        latest_col = closes.columns[-1]
        prev_col   = closes.columns[-2]

        # Change %
        change_pct = (closes[latest_col] - closes[prev_col]) / closes[prev_col] * 100

        # ROC
        for n in [5, 10, 20]:
            ref_col = closes.columns[-(n+1)] if n < len(closes.columns) - 1 else prev_col
            closes[f"roc{n}"] = (closes[latest_col] - closes[ref_col]) / closes[ref_col] * 100

        # MA20 / MA60
        for n in [20, 60]:
            ma = closes[closes.columns[-n:]].mean(axis=1)
            closes[f"above_ma{n}"] = (closes[latest_col] > ma).astype(int)

        result = pd.DataFrame({
            "symbol":      closes.index,
            "close":       closes[latest_col].values,
            "change_pct":  change_pct.values,
            "high":        highs[latest_col].values,
            "low":         lows[latest_col].values,
            "roc5":        closes["roc5"].values,
            "roc10":       closes["roc10"].values,
            "roc20":       closes["roc20"].values,
            "above_ma20":  closes["above_ma20"].values,
            "above_ma60":  closes["above_ma60"].values,
        })
        return result

    except Exception as e:
        print(f"[fetch_prices_batch] {e}")
        return pd.DataFrame()


def _empty_breadth():
    return {
        "advance": 0, "decline": 0, "flat": 0, "ad_ratio": 0,
        "ad_change": 0, "verdict": "⏳ Đang tải…",
        "highs_1m": 0, "lows_1m": 0, "trend_1m": "—",
        "highs_3m": 0, "lows_3m": 0, "trend_3m": "—",
        "roc5_up": 0, "roc5_down": 0, "roc5_avg": 0, "roc5_trend": "—",
        "roc10_up": 0, "roc10_down": 0, "roc10_avg": 0, "roc10_trend": "—",
        "roc20_up": 0, "roc20_down": 0, "roc20_avg": 0, "roc20_trend": "—",
        "ma20_above": 0, "ma20_below": 0, "ma20_pct": 0, "ma20_trend": "—",
        "ma60_above": 0, "ma60_below": 0, "ma60_pct": 0, "ma60_trend": "—",
    }
