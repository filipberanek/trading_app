"""
Trading Bot — Streamlit Dashboard

Čte přímo ze StateDB (SQLite). Nevyžaduje běžící API.
Spuštění:
    streamlit run dashboard.py
"""

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.engine.state_db import StateDB

DB_PATH = os.getenv("DB_PATH", "data/trading.db")

ASSET_COLORS = {
    "EQQQ": "#1f77b4",
    "IUCS": "#ff7f0e",
    "IGLN": "#2ca02c",
    "IBZL": "#9467bd",
    "EEA":  "#8c564b",
    "IUES": "#17becf",
    "SEGA": "#7f7f7f",
    "CASH": "#bcbd22",
}

st.set_page_config(
    page_title="Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Data ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_data():
    db = StateDB(DB_PATH)
    return {
        "heartbeat": db.get_latest_heartbeat(),
        "positions": db.get_latest_positions(),
        "portfolio": db.get_portfolio_history(days=365),
        "trades":    db.get_trades(limit=200),
        "signals":   db.get_signals(limit=30),
    }


data = load_data()
hb        = data["heartbeat"]
positions = data["positions"]
portfolio = data["portfolio"]
trades    = data["trades"]
signals   = data["signals"]

# ── Header ────────────────────────────────────────────────────────────────────

st.title("📈 Trading Bot Dashboard")

# ── Status bar ────────────────────────────────────────────────────────────────

if hb:
    last_ts = datetime.fromisoformat(hb["ts"])
    age_min = (datetime.now(tz=timezone.utc) - last_ts).total_seconds() / 60
    engine_alive = age_min < 10
    ibkr_ok      = hb["status"] == "OK"

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        label="Engine",
        value="✅ Běží" if engine_alive else "🔴 Nedostupný",
        delta=f"heartbeat před {age_min:.0f} min" if engine_alive else f"naposledy před {age_min:.0f} min",
        delta_color="normal" if engine_alive else "inverse",
    )
    col2.metric(
        label="IBKR spojení",
        value="✅ OK" if ibkr_ok else "🚨 Chyba",
        delta=hb.get("message") or "vše v pořádku",
        delta_color="normal" if ibkr_ok else "inverse",
    )

    current_symbol = positions[0]["symbol"] if positions else "CASH"
    current_qty    = positions[0]["quantity"] if positions else 0.0
    col3.metric(
        label="Aktuální pozice",
        value=current_symbol,
        delta=f"{current_qty:.4f} ks" if current_symbol != "CASH" else None,
    )

    portfolio_value = portfolio[-1]["total_value"] if portfolio else None
    col4.metric(
        label="Hodnota portfolia",
        value=f"{portfolio_value:,.2f} EUR" if portfolio_value else "—",
    )

    if not ibkr_ok and hb.get("message"):
        st.error(f"🚨 IBKR chyba: {hb['message']}")
    elif not engine_alive:
        st.warning(f"⚠️ Engine nekomunikuje. Poslední heartbeat před {age_min:.0f} minutami.")

else:
    st.warning("Žádná data z enginu. Engine ještě neběžel nebo je DB prázdná.")
    st.info("Spusť: `python main.py --mode paper --run-once`")

st.divider()

# ── Equity curve ──────────────────────────────────────────────────────────────

st.subheader("Historický vývoj portfolia")

if portfolio:
    df_eq = pd.DataFrame(portfolio)
    df_eq["ts"] = pd.to_datetime(df_eq["ts"])

    start_val = df_eq["total_value"].iloc[0]
    end_val   = df_eq["total_value"].iloc[-1]
    total_ret = (end_val / start_val - 1) * 100

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=df_eq["ts"],
        y=df_eq["total_value"],
        mode="lines",
        line=dict(color="#1f77b4", width=2),
        fill="tozeroy",
        fillcolor="rgba(31, 119, 180, 0.08)",
        hovertemplate="%{x|%d.%m.%Y %H:%M}: <b>%{y:,.2f} EUR</b><extra></extra>",
        name="Portfolio",
    ))
    fig_eq.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="EUR",
        xaxis_title=None,
        showlegend=False,
        hovermode="x unified",
        yaxis=dict(tickformat=",.0f"),
    )
    st.plotly_chart(fig_eq, use_container_width=True)
    st.caption(
        f"Počáteční hodnota: {start_val:,.2f} EUR  ·  "
        f"Aktuální: {end_val:,.2f} EUR  ·  "
        f"Celkový výnos: {total_ret:+.1f} %"
    )
else:
    st.info("Žádná data o vývoji portfolia. Data se zapisují po prvním obchodním cyklu.")

st.divider()

# ── Allocation timeline (rekonstruovaná z obchodů) ────────────────────────────

st.subheader("Historická alokace")

if trades:
    df_t = pd.DataFrame(trades)
    df_t["ts"] = pd.to_datetime(df_t["ts"])
    df_t = df_t.sort_values("ts").reset_index(drop=True)

    # Reconstruct position segments from trade log
    segments = []
    current_asset = "CASH"
    current_start = df_t["ts"].iloc[0]

    for _, row in df_t.iterrows():
        if row["action"] == "BUY":
            if current_asset != "CASH":
                segments.append({"asset": current_asset, "start": current_start, "end": row["ts"]})
            current_asset = row["symbol"]
            current_start = row["ts"]
        elif row["action"] == "SELL" and row["symbol"] == current_asset:
            segments.append({"asset": current_asset, "start": current_start, "end": row["ts"]})
            current_asset = "CASH"
            current_start = row["ts"]

    # Add open position if still holding
    if current_asset != "CASH":
        segments.append({
            "asset": current_asset,
            "start": current_start,
            "end": datetime.now(tz=timezone.utc),
        })

    if segments:
        df_seg = pd.DataFrame(segments)
        df_seg["start"] = pd.to_datetime(df_seg["start"])
        df_seg["end"]   = pd.to_datetime(df_seg["end"])

        fig_alloc = px.timeline(
            df_seg,
            x_start="start",
            x_end="end",
            y="asset",
            color="asset",
            color_discrete_map=ASSET_COLORS,
            labels={"asset": "Aktivum"},
        )
        fig_alloc.update_yaxes(autorange="reversed", title=None)
        fig_alloc.update_xaxes(title=None)
        fig_alloc.update_layout(
            height=260,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=True,
            legend_title="Aktivum",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig_alloc, use_container_width=True)
    else:
        st.info("Zatím žádné uzavřené pozice.")
else:
    st.info("Žádné obchody zatím.")

st.divider()

# ── Trades table ──────────────────────────────────────────────────────────────

st.subheader("Obchody")

if trades:
    df_trades = pd.DataFrame(trades)[
        ["ts", "symbol", "action", "quantity", "price", "portfolio_value", "reason"]
    ].copy()
    df_trades["ts"] = pd.to_datetime(df_trades["ts"]).dt.strftime("%d.%m.%Y %H:%M")
    df_trades = df_trades.rename(columns={
        "ts":              "Čas",
        "symbol":          "Aktivum",
        "action":          "Akce",
        "quantity":        "Množství",
        "price":           "Cena",
        "portfolio_value": "Hodnota portfolia",
        "reason":          "Důvod",
    })

    st.dataframe(
        df_trades,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Množství":         st.column_config.NumberColumn(format="%.4f"),
            "Cena":             st.column_config.NumberColumn(format="%.2f"),
            "Hodnota portfolia": st.column_config.NumberColumn(format="%.2f"),
        },
    )
else:
    st.info("Žádné obchody zatím.")

st.divider()

# ── Signals log ───────────────────────────────────────────────────────────────

with st.expander("Posledních 30 signálů"):
    if signals:
        df_sig = pd.DataFrame(signals)[
            ["ts", "symbol", "signal_type", "confidence", "executed"]
        ].copy()
        df_sig["ts"] = pd.to_datetime(df_sig["ts"]).dt.strftime("%d.%m.%Y %H:%M")
        df_sig["executed"] = df_sig["executed"].map({1: "✅", 0: "—"})
        df_sig = df_sig.rename(columns={
            "ts":          "Čas",
            "symbol":      "Aktivum",
            "signal_type": "Signál",
            "confidence":  "Spolehlivost",
            "executed":    "Vykonán",
        })
        st.dataframe(df_sig, use_container_width=True, hide_index=True)
    else:
        st.info("Žádné signály zatím.")

# ── Footer ────────────────────────────────────────────────────────────────────

st.caption(
    f"Data: {DB_PATH}  ·  "
    f"Obnovení: každých 60 s  ·  "
    f"Poslední načtení: {datetime.now().strftime('%H:%M:%S')}"
)
