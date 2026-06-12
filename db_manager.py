# File: db_manager.py
from supabase import create_client
from vnstock import stock_historical_data
from datetime import datetime, timedelta
import streamlit as st

def pump_data_to_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        supabase_client = create_client(url, key)

        tickers = ["SSI", "VND", "HPG", "FPT", "TCB", "MBB", "MWG", "VIC", "VHM", "VNM"]
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=1000)).strftime('%Y-%m-%d')

        for ticker in tickers:
            df = stock_historical_data(symbol=ticker, start_date=start_date, end_date=end_date, resolution="1D", type="stock")
            if df is not None and not df.empty:
                df.rename(columns={'time': 'date'}, inplace=True)
                df['ticker'] = ticker
                df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']]
                df['date'] = df['date'].astype(str)
                records = df.to_dict('records')
                
                supabase_client.table("stock_data").upsert(records).execute()
        return True, "🎉 ĐÃ BƠM XONG TOÀN BỘ DỮ LIỆU!"
    except Exception as e:
        return False, f"Lỗi: {e}"
