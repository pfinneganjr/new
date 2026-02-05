import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import talib  # For TA indicators
import time

# Function to fetch data for a given timeframe
def fetch_data(ticker, interval, period):
    try:
        data = yf.download(ticker, interval=interval, period=period)
        if data.empty:
            st.warning(f"No data found for {ticker} on {interval} timeframe. Try 'NQ=F' for futures.")
            return None
        return data
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

# Function to compute direction for a given dataframe
def get_direction(df):
    if df is None or len(df) < 100:  # Lowered to 100 for flexibility; TA-Lib handles small data with NaN
        return 0, 0, 0  # Neutral if insufficient data
    
    # Convert to contiguous 1D float arrays for TA-Lib compatibility (flatten to ensure 1D)
    close = np.ascontiguousarray(df['Close'].values.astype(float).flatten())
    high = np.ascontiguousarray(df['High'].values.astype(float).flatten())
    low = np.ascontiguousarray(df['Low'].values.astype(float).flatten())
    
    try:
        # RSI (14 periods, >50 bullish, <50 bearish)
        rsi_vals = talib.RSI(close, timeperiod=14)
        rsi = rsi_vals[-1] if len(rsi_vals) > 0 else np.nan
        bull_rsi = not np.isnan(rsi) and rsi > 50
        bear_rsi = not np.isnan(rsi) and rsi < 50
        
        # MACD (12,26,9, above signal bullish)
        macd, signal, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        bull_macd = not np.isnan(macd[-1]) and not np.isnan(signal[-1]) and macd[-1] > signal[-1]
        bear_macd = not np.isnan(macd[-1]) and not np.isnan(signal[-1]) and macd[-1] < signal[-1]
        
        # Moving Averages (EMA 50 and 200)
        ema50 = talib.EMA(close, timeperiod=50)[-1]
        ema200 = talib.EMA(close, timeperiod=200)[-1]
        bull_ma = not np.isnan(ema50) and not np.isnan(ema200) and close[-1] > ema50 and ema50 > ema200
        bear_ma = not np.isnan(ema50) and not np.isnan(ema200) and close[-1] < ema50 and ema50 < ema200
        
        # Support/Resistance (approx last pivot)
        pivot_high = np.max(high[-11:]) if len(high) >= 11 else np.nan
        pivot_low = np.min(low[-11:]) if len(low) >= 11 else np.nan
        bull_sr = not np.isnan(pivot_low) and close[-1] > pivot_low
        bear_sr = not np.isnan(pivot_high) and close[-1] < pivot_high
        
        # Scores
        bull_score = sum([bull_rsi, bull_macd, bull_ma, bull_sr])
        bear_score = sum([bear_rsi, bear_macd, bear_ma, bear_sr])
        
        dir = 1 if bull_score > bear_score else -1 if bear_score > bull_score else 0
        return dir, bull_score, bear_score
    except Exception as e:
        st.error(f"Indicator calculation error: {e}. Defaulting to neutral.")
        return 0, 0, 0

# Function to simulate entries/exits
def simulate_signals(ticker, df_1m, dir1, dir5, dir4h):
    if df_1m is None or len(df_1m) < 14:
        return None
    
    recent_df = df_1m.tail(15)
    # Convert to contiguous 1D float arrays (flatten to ensure 1D)
    high_recent = np.ascontiguousarray(recent_df['High'].values.astype(float).flatten())
    low_recent = np.ascontiguousarray(recent_df['Low'].values.astype(float).flatten())
    close_recent = np.ascontiguousarray(recent_df['Close'].values.astype(float).flatten())
    
    try:
        atr = talib.ATR(high_recent, low_recent, close_recent, timeperiod=14)[-1]
    except Exception as e:
        st.error(f"ATR calculation error: {e}")
        atr = np.nan
    
    signals = []
    if dir1 == 1 and dir4h == 1 and not np.isnan(atr):
        entry_price = close_recent[-1]
        sl = entry_price - 2 * atr
        tp = entry_price + 4 * atr
        signals.append(f"Long Entry: {entry_price:.2f}, SL: {sl:.2f}, TP: {tp:.2f} (Hold max 15 min)")
    
    if dir1 == -1 and dir4h == -1 and not np.isnan(atr):
        entry_price = close_recent[-1]
        sl = entry_price + 2 * atr
        tp = entry_price - 4 * atr
        signals.append(f"Short Entry: {entry_price:.2f}, SL: {sl:.2f}, TP: {tp:.2f} (Hold max 15 min)")
    
    return signals

# Streamlit App
st.title("Multi-Timeframe Market Direction Analyzer")

ticker = st.text_input("Enter Ticker Symbol (e.g., NQ=F for Nasdaq futures)", value="NQ=F").upper()
refresh_interval = st.number_input("Refresh Interval (seconds)", min_value=10, value=60, step=10)

if st.button("Start Analysis"):
    st.session_state.analyzing = True
    st.session_state.next_refresh = time.time() + refresh_interval

if st.button("Stop Analysis"):
    st.session_state.analyzing = False

if 'analyzing' in st.session_state and st.session_state.analyzing:
    with st.spinner("Fetching data..."):
        # Fetch with more periods for intraday
        df_1m = fetch_data(ticker, '1m', '5d')  # Increased for more bars
        df_5m = fetch_data(ticker, '5m', '10d')
        df_4h = fetch_data(ticker, '4h', '1y')
        
        # Get directions
        dir1, bull1, bear1 = get_direction(df_1m)
        dir5, bull5, bear5 = get_direction(df_5m)
        dir4h, bull4h, bear4h = get_direction(df_4h)
        
        # Create table data
        directions = {
            "Timeframe": ["1min", "5min", "4hr"],
            "Direction": [
                "Bullish" if dir1 == 1 else "Bearish" if dir1 == -1 else "Neutral",
                "Bullish" if dir5 == 1 else "Bearish" if dir5 == -1 else "Neutral",
                "Bullish" if dir4h == 1 else "Bearish" if dir4h == -1 else "Neutral"
            ],
            "Bull Score": [bull1, bull5, bull4h],
            "Bear Score": [bear1, bear5, bear4h]
        }
        st.table(pd.DataFrame(directions))
        
        # Simulate signals
        signals = simulate_signals(ticker, df_1m, dir1, dir5, dir4h)
        if signals:
            st.subheader("Potential Signals (Based on Latest Data)")
            for sig in signals:
                st.write(sig)
        else:
            st.info("No alignment for entry signals currently or insufficient data.")
    
    # Auto-refresh logic (non-blocking)
    if time.time() >= st.session_state.next_refresh:
        st.session_state.next_refresh = time.time() + refresh_interval
        st.rerun()