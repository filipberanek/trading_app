"""
Trading Bot — Streamlit Dashboard

Run with:
    streamlit run dashboard.py

Requires BE running at http://localhost:8000
    uvicorn src.api.main:app --reload --port 8000
"""

import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

API_URL = "http://localhost:8000"

ASSET_COLORS = {
    "EQQQ": "#1f77b4",
    "IUCS": "#ff7f0e",
    "IGLN": "#2ca02c",
    "IBZL": "#9467bd",
    "EEA":  "#8c564b",
    "IDTL": "#e377c2",
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


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch(endpoint: str):
    try:
        r = requests.get(f"{API_URL}{endpoint}", timeout=3)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


status = fetch("/api/status")
equity_data = fetch("/api/equity")
alloc_data = fetch("/api/allocation")
trades_data = fetch("/api/trades")

if not any([status, equity_data, alloc_data, trades_data]):
    st.error(
        f"Backend nedostupný ({API_URL}). "
        "Spusť: `uvicorn src.api.main:app --reload --port 8000`"
    )

# ── Header ────────────────────────────────────────────────────────────────────

st.title("📈 Trading Bot Dashboard")

# ── Status metrics ────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    label="Strategie",
    value=status["strategy"] if status else "—",
)
col2.metric(
    label="Aktuální pozice",
    value=status["current_asset"] if status else "—",
)
col3.metric(
    label="Alokace",
    value=f'{status["allocation_pct"]:.0%}' if status else "—",
)
col4.metric(
    label="Hodnota účtu",
    value=f'{status["account_value"]:,.2f} EUR' if status else "—",
)

st.divider()

# ── Equity curve ──────────────────────────────────────────────────────────────

st.subheader("Historický vývoj účtu")

if equity_data:
    df_eq = pd.DataFrame(equity_data)
    df_eq["date"] = pd.to_datetime(df_eq["date"])

    start_val = df_eq["value"].iloc[0]
    end_val = df_eq["value"].iloc[-1]
    total_ret = (end_val / start_val - 1) * 100

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=df_eq["date"],
        y=df_eq["value"],
        mode="lines",
        line=dict(color="#1f77b4", width=2),
        fill="tozeroy",
        fillcolor="rgba(31, 119, 180, 0.08)",
        hovertemplate="%{x|%d.%m.%Y}: <b>%{y:,.2f} EUR</b><extra></extra>",
        name="Účet",
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
        f"Počáteční kapitál: {start_val:,.2f} EUR  ·  "
        f"Aktuální hodnota: {end_val:,.2f} EUR  ·  "
        f"Celkový výnos: {total_ret:+.1f} %"
    )
else:
    st.info("Žádná data o vývoji účtu.")

st.divider()

# ── Allocation history ────────────────────────────────────────────────────────

st.subheader("Historická alokace (% účtu)")

if alloc_data:
    df_alloc = pd.DataFrame(alloc_data)
    df_alloc["start"] = pd.to_datetime(df_alloc["start"])
    df_alloc["end"]   = pd.to_datetime(df_alloc["end"])
    df_alloc["label"] = df_alloc.apply(
        lambda r: (
            f"{r['asset']}  "
            f"{r['start'].strftime('%d.%m.%Y')} – {r['end'].strftime('%d.%m.%Y')}"
        ),
        axis=1,
    )

    fig_alloc = px.timeline(
        df_alloc,
        x_start="start",
        x_end="end",
        y="asset",
        color="asset",
        color_discrete_map=ASSET_COLORS,
        hover_name="label",
        labels={"asset": "Aktivum"},
    )
    fig_alloc.update_yaxes(autorange="reversed", title=None)
    fig_alloc.update_xaxes(title=None)
    fig_alloc.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=True,
        legend_title="Aktivum",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig_alloc, use_container_width=True)
else:
    st.info("Žádná data o alokaci.")

st.divider()

# ── Trades table ──────────────────────────────────────────────────────────────

st.subheader("Historické obchody")

if trades_data:
    df_trades = pd.DataFrame(trades_data)
    df_trades = df_trades.rename(columns={
        "asset":        "Aktivum",
        "entry_date":   "Vstup (datum)",
        "entry_price":  "Vstupní cena",
        "exit_date":    "Výstup (datum)",
        "exit_price":   "Výstupní cena",
        "pnl":          "P&L (EUR)",
        "return_pct":   "Výnos (%)",
        "held_days":    "Dní drženo",
    })

    st.dataframe(
        df_trades,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Vstupní cena":  st.column_config.NumberColumn(format="%.2f"),
            "Výstupní cena": st.column_config.NumberColumn(format="%.2f"),
            "P&L (EUR)":     st.column_config.NumberColumn(format="%.2f"),
            "Výnos (%)":     st.column_config.NumberColumn(format="%.2f %%"),
        },
    )
else:
    st.info("Žádné obchody.")
