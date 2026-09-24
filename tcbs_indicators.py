"""
tcbs_indicators.py
==========================================================
CHỈ SỐ KỸ THUẬT & XẾP HẠNG TÍN HIỆU (GAUGE) — style TCBS
==========================================================
Ghi chú quan trọng (đọc trước khi dùng):

TCBS có 1 API nội bộ (tcinvest) trả sẵn các chỉ số kỹ thuật (SMA, RSI,
MACD, Bollinger, Stochastic, ADX...) và điểm "gauge" Buy/Sell/Neutral,
nhưng API đó gắn với phiên đăng nhập/connector riêng, KHÔNG phải một
REST endpoint public có thể gọi bằng requests.get() trần từ 1 script
GitHub Actions.

Ngược lại, phần intraday hiện có trong data_loader.py (_fetch_intraday_tcbs)
gọi thẳng "https://apipubaws.tcbs.com.vn/..." — đây là API public thật,
nhưng chỉ trả dữ liệu giá (OHLCV), KHÔNG có endpoint public đã xác nhận
cho "technical-indicator" hay "rating" nội bộ của TCBS.

=> Để không đoán bừa 1 endpoint riêng tư rồi ship code có thể gãy bất cứ
lúc nào, file này TỰ TÍNH các chỉ số kỹ thuật (SMA/EMA/RSI/MACD/Bollinger/
Stochastic/ADX) từ dữ liệu giá đã có sẵn trong data_loader.get_stock_data(),
rồi tổng hợp tín hiệu Buy/Sell/Neutral/Strong Buy/Strong Sell theo ĐÚNG
công thức ngưỡng mà TCBS công bố cho Gauge Chart của họ:

    action   = buy - sell
    available = buy + sell + neutral
    Strong Buy : action >=  3/5 * available
    Buy        : 1/5*available <= action <  3/5*available
    Neutral    : -1/5*available <= action < 1/5*available
    Sell       : -3/5*available <= action < -1/5*available
    Strong Sell: action < -3/5*available

Điểm "rating" tổng hợp kiểu TCBS (businessModel, financialHealth,
valuation...) dựa trên dữ liệu tài chính nội bộ mà TCBS không public,
nên KHÔNG được tính lại ở đây — chỉ phần kỹ thuật (TA) là tái tạo được
chính xác vì nó chỉ cần dữ liệu giá.
"""

import numpy as np
import pandas as pd
from datetime import datetime

import data_loader  # dùng lại nguồn giá đã có sẵn trong repo (VCI/MSN/DNSE/Yahoo)

# ==========================================================
# LƯU LỖI ĐỂ DEBUG (đồng bộ style với data_loader.LAST_ERRORS)
# ==========================================================
LAST_ERRORS: dict = {}


# ==========================================================
# CÁC HÀM TÍNH CHỈ BÁO KỸ THUẬT THUẦN PANDAS (không cần talib)
# ==========================================================
def _sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period, min_periods=period).mean()


def _ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = _sma(close, period)
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, lower


def _stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    low_min = df["low"].rolling(window=k_period, min_periods=k_period).min()
    high_max = df["high"].rolling(window=k_period, min_periods=k_period).max()
    stochk = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    stochd = stochk.rolling(window=d_period, min_periods=d_period).mean()
    return stochk.fillna(50), stochd.fillna(50)


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean() / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx.fillna(0)


# ==========================================================
# PUBLIC API #1 — BẢNG CHỈ SỐ KỸ THUẬT THEO NGÀY
# (đúng bộ cột mà TCBS trả về: sma5, sma20, upper, lower, macd,
#  macdema, macdhist, stochk, stochd, rsi, adx, dateReport)
# ==========================================================
def get_technical_indicator(ticker: str, days_back: int = 250) -> pd.DataFrame:
    """
    Trả về DataFrame lịch sử các chỉ báo kỹ thuật cho `ticker`, tính từ
    dữ liệu giá của data_loader.get_stock_data(). Mỗi dòng ứng với 1
    phiên giao dịch, mới nhất ở cuối.
    """
    key = f"get_technical_indicator|{ticker}"
    try:
        df = data_loader.get_stock_data(ticker, days_back=days_back + 60)
        if df is None or df.empty or len(df) < 30:
            LAST_ERRORS[key] = "Không đủ dữ liệu giá để tính chỉ báo (cần >= 30 phiên)."
            return pd.DataFrame()

        df = df.sort_values("time").reset_index(drop=True)
        close = df["close"]

        sma5 = _sma(close, 5)
        sma20 = _sma(close, 20)
        upper, lower = _bollinger(close, 20, 2)
        macd_line, macd_signal, macd_hist = _macd(close, 12, 26, 9)
        stochk, stochd = _stochastic(df, 14, 3)
        rsi = _rsi(close, 14)
        adx = _adx(df, 14)

        out = pd.DataFrame(
            {
                "ticker": ticker,
                "closePrice": close,
                "sma5": sma5,
                "sma20": sma20,
                "upper": upper,
                "lower": lower,
                "macd": macd_line,
                "macdema": macd_signal,
                "macdhist": macd_hist,
                "stochk": stochk,
                "stochd": stochd,
                "rsi": rsi,
                "adx": adx,
                "dateReport": df["time"].dt.strftime("%d/%m/%Y"),
            }
        )
        out = out.dropna(subset=["sma20", "rsi"]).tail(days_back).reset_index(drop=True)
        LAST_ERRORS.pop(key, None)
        return out
    except Exception as e:
        LAST_ERRORS[key] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()


# ==========================================================
# PUBLIC API #2 — GAUGE SIGNAL (Strong Buy...Strong Sell)
# ==========================================================
def _classify(action: float, available: float) -> str:
    if available <= 0:
        return "Neutral"
    if action >= 3 / 5 * available:
        return "Strong Buy"
    if action >= 1 / 5 * available:
        return "Buy"
    if action >= -1 / 5 * available:
        return "Neutral"
    if action >= -3 / 5 * available:
        return "Sell"
    return "Strong Sell"


def _sig(value, buy_cond, sell_cond) -> str:
    if buy_cond:
        return "Buy"
    if sell_cond:
        return "Sell"
    return "Neutral"


def get_gauge_signal(ticker: str) -> dict:
    """
    Tổng hợp tín hiệu kỹ thuật kiểu "Gauge Chart" của TCBS: gộp tín hiệu
    từ các chỉ báo dao động (RSI, Stochastic, MACD Histogram, vị trí so
    với dải Bollinger) + 6 đường SMA + 6 đường EMA (5/10/20/50/100/200),
    theo đúng công thức ngưỡng TCBS công bố (Strong Buy/Buy/Neutral/
    Sell/Strong Sell dựa trên buy-sell / (buy+sell+neutral)).
    """
    key = f"get_gauge_signal|{ticker}"
    ta = get_technical_indicator(ticker, days_back=210)
    if ta.empty:
        LAST_ERRORS[key] = "Không có dữ liệu chỉ báo để tính gauge."
        return {}

    df = data_loader.get_stock_data(ticker, days_back=260)
    if df is None or df.empty:
        LAST_ERRORS[key] = "Không có dữ liệu giá để tính gauge."
        return {}
    df = df.sort_values("time").reset_index(drop=True)
    close = df["close"]
    last_close = float(close.iloc[-1])

    last = ta.iloc[-1]

    # ---- Nhóm chỉ báo dao động (oscillators) ----
    osc_signals = {
        "rsi": _sig(last["rsi"], last["rsi"] < 30, last["rsi"] > 70),
        "stochk": _sig(last["stochk"], last["stochk"] < 20, last["stochk"] > 80),
        "macdhist": _sig(last["macdhist"], last["macdhist"] > 0, last["macdhist"] < 0),
        "bollinger": _sig(
            last_close,
            last_close < last["lower"],
            last_close > last["upper"],
        ),
    }
    osc_buy = sum(1 for v in osc_signals.values() if v == "Buy")
    osc_sell = sum(1 for v in osc_signals.values() if v == "Sell")
    osc_neutral = sum(1 for v in osc_signals.values() if v == "Neutral")

    # ---- 6 đường SMA & 6 đường EMA: Buy nếu Close > MA, Sell nếu Close < MA ----
    periods = [5, 10, 20, 50, 100, 200]
    simple, exponential = {}, {}
    for p in periods:
        sma_p = float(_sma(close, p).iloc[-1]) if len(close) >= p else np.nan
        ema_p = float(_ema(close, p).iloc[-1]) if len(close) >= p else np.nan
        simple[f"ma{p}"] = {
            "value": None if np.isnan(sma_p) else round(sma_p, 2),
            "signal": "Neutral" if np.isnan(sma_p) else _sig(sma_p, last_close > sma_p, last_close < sma_p),
        }
        exponential[f"ma{p}"] = {
            "value": None if np.isnan(ema_p) else round(ema_p, 2),
            "signal": "Neutral" if np.isnan(ema_p) else _sig(ema_p, last_close > ema_p, last_close < ema_p),
        }

    simple_buy = sum(1 for v in simple.values() if v["signal"] == "Buy")
    simple_sell = sum(1 for v in simple.values() if v["signal"] == "Sell")
    simple_neutral = sum(1 for v in simple.values() if v["signal"] == "Neutral")

    exp_buy = sum(1 for v in exponential.values() if v["signal"] == "Buy")
    exp_sell = sum(1 for v in exponential.values() if v["signal"] == "Sell")
    exp_neutral = sum(1 for v in exponential.values() if v["signal"] == "Neutral")

    def _pack(buy, sell, neutral):
        action = buy - sell
        available = buy + sell + neutral
        return {"buy": buy, "sell": -sell, "neutral": neutral, "signal": _classify(action, available)}

    result = {
        "ticker": ticker,
        "lastClose": last_close,
        "dateReport": last["dateReport"],
        "indicator": {**osc_signals, "signal": _pack(osc_buy, osc_sell, osc_neutral)},
        "simple": {**simple, "signal": _pack(simple_buy, simple_sell, simple_neutral)},
        "exponential": {**exponential, "signal": _pack(exp_buy, exp_sell, exp_neutral)},
        "average": _pack(simple_buy + exp_buy, simple_sell + exp_sell, simple_neutral + exp_neutral),
        "summary": _pack(
            osc_buy + simple_buy + exp_buy,
            osc_sell + simple_sell + exp_sell,
            osc_neutral + simple_neutral + exp_neutral,
        ),
    }
    LAST_ERRORS.pop(key, None)
    return result


# ==========================================================
# CHẠY THỬ TRỰC TIẾP: python tcbs_indicators.py FPT
# ==========================================================
if __name__ == "__main__":
    import sys

    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "FPT"
    print(f"=== Chỉ số kỹ thuật {symbol} ===")
    ta_df = get_technical_indicator(symbol, days_back=10)
    print(ta_df.to_string(index=False))

    print(f"\n=== Gauge signal {symbol} ===")
    gauge = get_gauge_signal(symbol)
    print(f"Ngày: {gauge.get('dateReport')} | Giá đóng cửa: {gauge.get('lastClose')}")
    print(f"Tổng hợp (summary): {gauge.get('summary')}")
    if LAST_ERRORS:
        print("\nLỗi ghi nhận:", LAST_ERRORS)
