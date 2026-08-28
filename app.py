import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random
from check_signal import get_trading_signal

# ============================================================
# REAL SIGNAL FUNCTION
# ============================================================
# check_signal.py mein apna core logic ek function ke andar
# wrap kar dein (dict return kare, print nahi), phir yahan
# import uncomment karein:
#
#   from check_signal import get_trading_signal
#
# get_trading_signal(symbol, timeframe) is dict jaisa return kare:
# {
#   "symbol": "XAU/USD", "price": 4345.16285, "pattern": "Hammer",
#   "rsi": 43.8, "ml_signal": "Down", "ml_confidence": 88.0,
#   "signal_strength": "Strong", "trend_next_5_candles": "N/A",
#   "trend_next_5_confidence": 0, "possible_target_up": 4350.28494,
#   "possible_target_down": 4344.32519,
#   "knowledge_matches": ["Hammer", "Pattern Context Matters More Than Shape Alone", "Inverted Hammer"],
#   "news_risk_level": "high", "explanation": "..."
# }
USE_REAL_MODEL = True  # True karein jab import uncomment kar dein

if USE_REAL_MODEL:
    from check_signal import get_trading_signal

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Zentrix AI Trading Assistant",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CUSTOM STYLING
# ============================================================
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric {
        background-color: #1c1f26;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2b2f3a;
    }
    div[data-testid="stMetricLabel"] {
        color: #9aa4b2 !important;
        font-size: 14px;
    }
    div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 26px;
        font-weight: 700;
    }
    .risk-high { color: #ff4b4b; font-weight: 600; }
    .risk-medium { color: #f2c94c; font-weight: 600; }
    .risk-low { color: #00d09c; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR - Controls
# ============================================================
st.sidebar.title("⚙️ Zentrix Controls")
st.sidebar.markdown("---")

pair = st.sidebar.selectbox(
    "Select Currency / Asset Pair:",
    ["XAU/USD", "BTC/USD", "EUR/USD", "GBP/USD"]
)

timeframe = st.sidebar.radio(
    "Timeframe:",
    ["1m", "15m", "1h", "4h"],
    horizontal=False
)

st.sidebar.markdown("---")
if not USE_REAL_MODEL:
    st.sidebar.caption("⚠️ Testing Mode — sample data shown. Set USE_REAL_MODEL = True in code once check_signal.py is connected.")
else:
    st.sidebar.caption("🟢 Connected to live ML engine.")

# ============================================================
# HEADER
# ============================================================
col_logo, col_status = st.columns([4, 1])
with col_logo:
    st.title("Zentrix 📈 — AI Trading Assistant")
    st.caption("Live AI-generated trading signals across forex, crypto & commodities")
with col_status:
    st.markdown("###")
    st.success("🟢 Live")

st.markdown("---")

# ============================================================
# DUMMY DATA (matches real check_signal.py output schema)
# Testing k liye — jab USE_REAL_MODEL = True hoga, ye use nahi hoga
# ============================================================
def get_dummy_signal(symbol, tf):
    random.seed(hash(symbol + tf + str(datetime.now().minute)) % 1000)
    ml_signal = random.choice(["Up", "Down", "Sideways"])
    confidence = round(random.uniform(55, 92), 1)
    strength = "Strong" if confidence > 80 else "Good" if confidence > 65 else "Weak"
    rsi = round(random.uniform(25, 78), 1)
    base_price = 4345.16 if "XAU" in symbol else 60000 if "BTC" in symbol else 1.09
    pattern = random.choice(["Hammer", "Inverted Hammer", "Doji", "Engulfing", "Shooting Star"])
    news_risk = random.choice(["low", "medium", "high"])
    target_up = round(base_price + base_price * 0.0012, 5)
    target_down = round(base_price - base_price * 0.0012, 5)
    return {
        "symbol": symbol,
        "price": base_price,
        "pattern": pattern,
        "rsi": rsi,
        "ml_signal": ml_signal,
        "ml_confidence": confidence,
        "signal_strength": strength,
        "trend_next_5_candles": random.choice(["Up", "Down", "N/A"]),
        "trend_next_5_confidence": round(random.uniform(0, 70), 1),
        "possible_target_up": target_up,
        "possible_target_down": target_down,
        "knowledge_matches": [pattern, "Pattern Context Matters More Than Shape Alone"],
        "news_risk_level": news_risk,
        "explanation": "Model detected a "
                        f"{pattern} pattern with RSI at {rsi}, suggesting a "
                        f"{ml_signal.lower()} bias in the short term.",
    }

def get_dummy_price_history(symbol, points=50):
    random.seed(hash(symbol) % 1000)
    base = 4345 if "XAU" in symbol else 60000 if "BTC" in symbol else 1.09
    prices = [base]
    for _ in range(points - 1):
        change = np.random.normal(0, base * 0.0015)
        prices.append(prices[-1] + change)
    times = [datetime.now() - timedelta(minutes=(points - i) * 15) for i in range(points)]
    return pd.DataFrame({"time": times, "price": prices})

# ============================================================
# MAIN ACTION BUTTON
# ============================================================
generate = st.button("🔍 Generate AI Signal", use_container_width=True, type="primary")

if generate:
    with st.spinner(f"Analyzing live market data for {pair} & running AI models..."):
        try:
            if USE_REAL_MODEL:
                result = get_trading_signal(pair, timeframe)
            else:
                result = get_dummy_signal(pair, timeframe)
            price_df = get_dummy_price_history(pair)  # chart abhi bhi sample rahega jab tak real OHLC source add na ho

            # ---------------- Top Summary Cards ----------------
            st.success(f"✅ Signal generated for **{result['symbol']}**")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("ML Signal", result["ml_signal"])
            c2.metric("Confidence", f"{result['ml_confidence']}%")
            c3.metric("Signal Strength", result["signal_strength"])
            c4.metric("Current Price", f"${result['price']:,}")

            st.markdown("---")

            # ---------------- Price Chart ----------------
            st.subheader(f"📊 {result['symbol']} — Price Movement")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=price_df["time"], y=price_df["price"],
                mode="lines", line=dict(color="#00d09c", width=2),
                fill="tozeroy", fillcolor="rgba(0,208,156,0.1)"
            ))
            fig.update_layout(
                template="plotly_dark", height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title="Time", yaxis_title="Price"
            )
            st.plotly_chart(fig, use_container_width=True)

            # ---------------- RSI + Pattern + Targets ----------------
            col_a, col_b = st.columns([1, 2])

            with col_a:
                st.subheader("📉 RSI Indicator")
                rsi_fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=result["rsi"],
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": "#00d09c"},
                        "steps": [
                            {"range": [0, 30], "color": "#1c1f26"},
                            {"range": [30, 70], "color": "#2b2f3a"},
                            {"range": [70, 100], "color": "#1c1f26"},
                        ],
                    }
                ))
                rsi_fig.update_layout(height=230, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(rsi_fig, use_container_width=True)

                st.markdown(f"**Candlestick Pattern:** {result['pattern']}")
                risk_class = f"risk-{result['news_risk_level']}"
                st.markdown(
                    f"**News Risk Level:** "
                    f"<span class='{risk_class}'>{result['news_risk_level'].upper()}</span>",
                    unsafe_allow_html=True
                )

            with col_b:
                st.subheader("🧠 AI Analysis Summary")
                st.write(f"""
                - **Pair analyzed:** {result['symbol']}
                - **Timeframe:** {timeframe}
                - **Recommended action:** {result['ml_signal']}
                - **Model confidence:** {result['ml_confidence']}% ({result['signal_strength']} signal)
                - **RSI reading:** {result['rsi']} — {"Overbought zone" if result['rsi'] > 70 else "Oversold zone" if result['rsi'] < 30 else "Neutral zone"}
                - **Next 5 candles trend:** {result['trend_next_5_candles']} ({result['trend_next_5_confidence']}% confidence)
                - **Possible target (up):** ${result['possible_target_up']:,}
                - **Possible target (down):** ${result['possible_target_down']:,}
                """)

                st.markdown("**Supporting knowledge base matches:**")
                for match in result["knowledge_matches"]:
                    st.markdown(f"- {match}")

                with st.expander("📖 Full explanation"):
                    st.write(result["explanation"])

        except Exception as e:
            st.error(f"Error generating signal: {e}")

else:
    st.info("👆 Select a pair from the sidebar and click **Generate AI Signal** to see live analysis.")

# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("Zentrix AI Trading Assistant — Demo build for testing purposes. Not financial advice.")