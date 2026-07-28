"""
scan_breadth_daily.py
Chạy qua GitHub Actions — KHÔNG dùng data_loader.py (phụ thuộc streamlit).
Tự cào dữ liệu vnstock trực tiếp.
"""
import json
import time
import os
import concurrent.futures
from datetime import datetime
from pathlib import Path

import pandas as pd

OUTPUT_LATEST = Path("breadth_latest.json")
OUTPUT_HISTORY = Path("breadth_history.json")
MAX_HISTORY_DAYS = 90
MAX_WORKERS = 4
MIN_BARS = 51

# ── breadth_score logic (inline, tránh import phụ thuộc) ─────────────────────

def _ad_score(ad_pct):
    for threshold, score in [(75,4),(60,3),(50,2),(42,1),(35,0),(25,-1),(18,-2),(10,-3)]:
        if ad_pct >= threshold: return score
    return -4

def _trend_score(pct_ma50):
    for threshold, score in [(75,4),(60,3),(50,2),(40,1),(30,0),(20,-1),(12,-2),(6,-3)]:
        if pct_ma50 >= threshold:
