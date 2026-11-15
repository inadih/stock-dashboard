"""Dashboard de recherche boursière : S&P 500, semi-conducteurs et quantique.

Lancement :  .venv\\Scripts\\streamlit run app.py
"""

from __future__ import annotations

import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

import data
import sec
from universes import UNIVERSES

st.set_page_config(page_title="Stock Research", page_icon="📈", layout="wide")


# --------------------------------------------------------------------------- #
# Chargement (mis en cache par Streamlit en plus du cache disque)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def load_universe(name: str) -> pd.DataFrame:
    return UNIVERSES[name]()


def load_screener(name: str, progress=None) -> pd.DataFrame:
    """Tableau d'un univers, gardé une heure en mémoire de session.

    (Pas de st.cache_data ici : la barre de progression affichée pendant le
    chargement est incompatible avec ce cache.)
    """
    store = st.session_state.setdefault("screeners", {})
    hit = store.get(name)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    df = data.build_screener(load_universe(name), progress=progress)
    store[name] = (time.time(), df)
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_financials(ticker: str, quarterly: bool) -> pd.DataFrame:
    return data.financials(ticker, quarterly=quarterly)


@st.cache_data(ttl=3600, show_spinner="Lecture des rapports SEC…")
def load_sec(ticker: str, quarterly: bool):
    """(données, message d'erreur) — l'erreur est renvoyée plutôt que levée."""
    try:
        return sec.statements(ticker, quarterly=quarterly), None
    except Exception as exc:
        return None, str(exc)


@st.cache_data(ttl=3600, show_spinner=False)
def load_filings(ticker: str) -> pd.DataFrame:
    return sec.filings(ticker)


@st.cache_data(ttl=900, show_spinner=False)
def load_history(ticker: str, period: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(period=period, auto_adjust=True)


def fmt_usd(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    for div, unit in ((1e12, " T$"), (1e9, " Md$"), (1e6, " M$")):
        if abs(x) >= div:
            return f"{x / div:,.1f}{unit}".replace(",", " ")
    return f"{x:,.0f} $".replace(",", " ")


def fmt_pct(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x * 100:+.1f} %"


# --------------------------------------------------------------------------- #
# Barre latérale
# --------------------------------------------------------------------------- #
st.sidebar.title("📈 Stock Research")
universe_name = st.sidebar.radio("Univers", list(UNIVERSES))

if st.sidebar.button("🔄 Rafraîchir les données", help="Vide le cache de la session"):
    st.cache_data.clear()
    st.session_state.pop("screeners", None)

st.sidebar.caption(
    "Données : Yahoo Finance (via yfinance). Elles peuvent être en retard, "
    "incomplètes ou fausses : vérifiez dans les rapports officiels avant "
    "toute conclusion. Ce dashboard est un outil d'analyse, pas un conseil "
    "en investissement."
)

# --------------------------------------------------------------------------- #
# Données de l'univers
# --------------------------------------------------------------------------- #
bar = st.progress(0.0, text="Chargement de l'univers…")
try:
    screener = load_screener(universe_name, progress=lambda p, t: bar.progress(p, text=t))
except Exception as exc:  # réseau coupé, Yahoo indisponible…
    bar.empty()
    st.error(f"Impossible de charger les données : {exc}")
    st.stop()
bar.empty()

segments = sorted(screener["segment"].dropna().unique())
chosen = st.sidebar.multiselect("Filtrer par secteur / segment", segments)
view = screener[screener["segment"].isin(chosen)] if chosen else screener
missing = view["market_cap_usd"].isna().sum()

st.title(universe_name)
if missing:
    st.caption(f"⚠️ {missing} entreprise(s) sans données Yahoo pour l'instant (ticker introuvable ou limite de requêtes).")

tab_overview, tab_compare, tab_company = st.tabs(
    ["Vue d'ensemble", "Comparer", "Fiche entreprise"]
)

# --------------------------------------------------------------------------- #
# Vue d'ensemble
# --------------------------------------------------------------------------- #
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entreprises", f"{view['market_cap_usd'].notna().sum()} / {len(view)}")
    c2.metric("Capitalisation totale", fmt_usd(view["market_cap_usd"].sum()))
    c3.metric("P/E prévisionnel médian", f"{view['forwardPE'].median():.1f}" if view["forwardPE"].notna().any() else "—")
    c4.metric("Croissance du CA médiane", fmt_pct(view["revenueGrowth"].median()))

    tm = view.dropna(subset=["market_cap_usd"]).copy()
    if not tm.empty:
        tm["perf_ytd_pct"] = tm["perf_ytd"] * 100
        fig = px.treemap(
            tm, path=[px.Constant(universe_name), "segment", "ticker"],
            values="market_cap_usd", color="perf_ytd_pct",
            color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
            range_color=(-50, 50), hover_data={"name": True, "perf_ytd_pct": ":.1f"},
        )
        fig.update_layout(margin=dict(t=30, l=0, r=0, b=0), height=520,
                          coloraxis_colorbar_title="Perf. depuis<br>le 1er janv. (%)")
        st.plotly_chart(fig, width="stretch")
        st.caption("Taille = capitalisation en dollars · couleur = performance depuis le 1er janvier (devise locale).")

    table = view[[
        "ticker", "name", "segment", "country", "market_cap_usd", "revenue_usd",
        "revenueGrowth", "grossMargins", "operatingMargins", "trailingPE",
        "forwardPE", "enterpriseToEbitda", "fcf_yield", "net_cash_usd",
        "perf_1m", "perf_ytd", "perf_1y",
    ]].copy()
    pct_cols = ["revenueGrowth", "grossMargins", "operatingMargins", "fcf_yield",
                "perf_1m", "perf_ytd", "perf_1y"]
    table[pct_cols] = table[pct_cols] * 100
    for col in ["market_cap_usd", "revenue_usd", "net_cash_usd"]:
        table[col] = table[col] / 1e9
    st.dataframe(
        table.sort_values("market_cap_usd", ascending=False),
        hide_index=True, width="stretch", height=560,
        column_config={
            "ticker": "Ticker", "name": "Entreprise", "segment": "Segment",
            "country": "Pays",
            "market_cap_usd": st.column_config.NumberColumn("Capi. (Md$)", format="%.1f"),
            "revenue_usd": st.column_config.NumberColumn("CA 12 mois (Md$)", format="%.1f"),
            "revenueGrowth": st.column_config.NumberColumn("Croiss. CA (%)", format="%.1f"),
            "grossMargins": st.column_config.NumberColumn("Marge brute (%)", format="%.1f"),
            "operatingMargins": st.column_config.NumberColumn("Marge op. (%)", format="%.1f"),
            "trailingPE": st.column_config.NumberColumn("P/E", format="%.1f"),
            "forwardPE": st.column_config.NumberColumn("P/E prév.", format="%.1f"),
            "enterpriseToEbitda": st.column_config.NumberColumn("VE/EBITDA", format="%.1f"),
            "fcf_yield": st.column_config.NumberColumn("Rendement FCF (%)", format="%.1f"),
            "net_cash_usd": st.column_config.NumberColumn("Trésorerie nette (Md$)", format="%.1f"),
            "perf_1m": st.column_config.NumberColumn("Perf. 1 mois (%)", format="%.1f"),
            "perf_ytd": st.column_config.NumberColumn("Perf. 1er janv. (%)", format="%.1f"),
            "perf_1y": st.column_config.NumberColumn("Perf. 1 an (%)", format="%.1f"),
        },
    )
    st.download_button(
        "⬇️ Exporter en CSV", table.to_csv(index=False).encode("utf-8"),
        file_name=f"{universe_name}.csv", mime="text/csv",
    )

# --------------------------------------------------------------------------- #
# Comparer
# --------------------------------------------------------------------------- #
METRICS = {
    "Croissance du CA (%)": ("revenueGrowth", 100),
    "Marge brute (%)": ("grossMargins", 100),
    "Marge opérationnelle (%)": ("operatingMargins", 100),
    "P/E prévisionnel": ("forwardPE", 1),
    "VE/EBITDA": ("enterpriseToEbitda", 1),
    "Prix / ventes": ("priceToSalesTrailing12Months", 1),
    "Rendement FCF (%)": ("fcf_yield", 100),
    "Perf. depuis le 1er janv. (%)": ("perf_ytd", 100),
    "Perf. 1 an (%)": ("perf_1y", 100),
    "Capitalisation (Md$)": ("market_cap_usd", 1e-9),
}

with tab_compare:
    left, right = st.columns(2)
    x_label = left.selectbox("Axe horizontal", list(METRICS), index=0)
    y_label = right.selectbox("Axe vertical", list(METRICS), index=3)
    (xc, xm), (yc, ym) = METRICS[x_label], METRICS[y_label]
    sc = view.dropna(subset=[xc, yc, "market_cap_usd"]).copy()
    sc["x"], sc["y"] = sc[xc] * xm, sc[yc] * ym
    if sc.empty:
        st.info("Pas assez de données pour ce couple d'indicateurs.")
    else:
        fig = px.scatter(
            sc, x="x", y="y", size="market_cap_usd", color="segment",
            hover_name="name", text="ticker", size_max=45,
            labels={"x": x_label, "y": y_label, "segment": "Segment"},
        )
        fig.update_traces(textposition="top center", textfont_size=10)
        fig.update_layout(height=560)
        st.plotly_chart(fig, width="stretch")
        st.caption("Taille des bulles = capitalisation. Les valeurs extrêmes (P/E de 300…) écrasent parfois le graphique : zoomez avec la souris.")

    rank_label = st.selectbox("Classement par indicateur", list(METRICS), index=6)
    rc, rm = METRICS[rank_label]
    ranked = view.dropna(subset=[rc]).assign(v=lambda d: d[rc] * rm).sort_values("v", ascending=False).head(30)
    if not ranked.empty:
        fig = px.bar(ranked, x="ticker", y="v", color="segment", hover_name="name",
                     labels={"v": rank_label, "ticker": ""})
        fig.update_layout(height=420)
        st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------- #
# Fiche entreprise
# --------------------------------------------------------------------------- #
with tab_company:
    options = view.sort_values("market_cap_usd", ascending=False)
    labels = {r.ticker: f"{r.ticker} — {r.name}" for r in options.itertuples()}
    ticker = st.selectbox("Entreprise", list(labels), format_func=labels.get)
    row = screener.set_index("ticker").loc[ticker]

    long_name = row.get("longName")
    st.subheader(f"{long_name if isinstance(long_name, str) else row['name']}  ·  {ticker}")
    st.caption(" · ".join(str(v) for v in [row.get("country"), row.get("sector"), row.get("industry")] if isinstance(v, str)))

    k = st.columns(3) + st.columns(3)
    k[0].metric("Capitalisation", fmt_usd(row["market_cap_usd"]))
    k[1].metric("CA 12 mois", fmt_usd(row["revenue_usd"]), fmt_pct(row["revenueGrowth"]))
    k[2].metric("Marge opérationnelle", fmt_pct(row["operatingMargins"]).lstrip("+"))
    k[3].metric("P/E prévisionnel", f"{row['forwardPE']:.1f}" if pd.notna(row["forwardPE"]) else "—")
    k[4].metric("Free cash flow", fmt_usd(row["fcf_usd"]))
    k[5].metric("Trésorerie nette", fmt_usd(row["net_cash_usd"]))

    # --- Cours de bourse -------------------------------------------------- #
    period = st.radio("Période", ["6mo", "1y", "2y", "5y", "max"], index=2, horizontal=True,
                      format_func={"6mo": "6 mois", "1y": "1 an", "2y": "2 ans", "5y": "5 ans", "max": "Tout"}.get)
    hist = load_history(ticker, period)
    if hist.empty:
        st.info("Pas d'historique de cours disponible.")
    else:
        close = hist["Close"]
        fig = go.Figure()
        fig.add_scatter(x=close.index, y=close, name="Cours", line=dict(width=2))
        for win, dash in ((50, "dot"), (200, "dash")):
            if len(close) > win:
                fig.add_scatter(x=close.index, y=close.rolling(win).mean(),
                                name=f"Moyenne {win} j", line=dict(width=1, dash=dash))
        fig.update_layout(height=380, margin=dict(t=20, b=20),
                          yaxis_title=f"Cours ({row.get('currency') or ''})",
                          legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, width="stretch")

    # --- Fondamentaux ----------------------------------------------------- #
    c_src, c_freq = st.columns(2)
    freq = c_freq.radio("Fréquence des comptes", ["Trimestriel", "Annuel"], horizontal=True)
    quarterly = freq == "Trimestriel"
    sec_data, sec_error = load_sec(ticker, quarterly)
    source_options = (["SEC EDGAR (officiel)"] if sec_data else []) + ["Yahoo Finance"]
    source = c_src.radio("Source des comptes", source_options, horizontal=True)
    from_sec = source.startswith("SEC")
    if sec_error:
        st.caption(f"⚠️ SEC EDGAR indisponible pour l'instant : {sec_error}")
    elif not sec_data:
        st.caption("ℹ️ Cette entreprise ne dépose pas de rapports à la SEC (cotation hors des États-Unis) : comptes Yahoo uniquement.")

    if from_sec:
        fin = sec_data["table"].copy()
        cur = sec_data["currency"] or ""
        if {"Flux de trésorerie opérationnel", "Capex"} <= set(fin.index):
            fin.loc["Free cash flow"] = fin.loc["Flux de trésorerie opérationnel"] - fin.loc["Capex"].abs()
        flows = fin.drop(index=[r for r in sec.INSTANT if r in fin.index])
        if quarterly and flows.dropna(how="all").empty:
            st.info("Cette entreprise ne publie que des comptes annuels à la SEC (rapport 20-F) : choisissez « Annuel ».")
    else:
        fin = load_financials(ticker, quarterly)
        cur = row.get("financialCurrency") or row.get("currency") or ""
    if fin.empty:
        st.info("Pas de comptes détaillés disponibles pour cette entreprise avec cette source.")
    else:
        plot_rows = [r for r in ["Chiffre d'affaires", "Résultat opérationnel", "Free cash flow"] if r in fin.index]
        long = fin.loc[plot_rows].T.reset_index(names="Période").melt("Période", var_name="Ligne", value_name="Montant")
        fig = px.bar(long, x="Période", y="Montant", color="Ligne", barmode="group",
                     labels={"Montant": f"Montant ({cur})"})
        fig.update_layout(height=380, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, width="stretch")

        # Ratios inspirés de l'analyse « qualité des résultats »
        ratios = {}
        if {"Capex", "Amortissements (D&A)"} <= set(fin.index):
            ratios["Capex / amortissements (×)"] = fin.loc["Capex"].abs() / fin.loc["Amortissements (D&A)"].abs()
        if {"Flux de trésorerie opérationnel", "Capex"} <= set(fin.index):
            ratios["Part du capex financée par l'activité (%)"] = (
                fin.loc["Flux de trésorerie opérationnel"] / fin.loc["Capex"].abs() * 100
            )
        if {"Rémunération en actions (SBC)", "Chiffre d'affaires"} <= set(fin.index):
            ratios["SBC / chiffre d'affaires (%)"] = (
                fin.loc["Rémunération en actions (SBC)"] / fin.loc["Chiffre d'affaires"] * 100
            )
        if {"R&D", "Chiffre d'affaires"} <= set(fin.index):
            ratios["R&D / chiffre d'affaires (%)"] = fin.loc["R&D"] / fin.loc["Chiffre d'affaires"] * 100
        if ratios:
            st.markdown("**Ratios de qualité des résultats**")
            st.dataframe(pd.DataFrame(ratios).T.round(1), width="stretch")
            st.caption(
                "Capex / amortissements ≈ 1 pour une entreprise mature ; bien au-dessus = phase "
                "d'investissement lourd. Une SBC élevée et croissante gonfle les résultats « ajustés »."
            )

        st.markdown(f"**Comptes détaillés** (en millions de {cur})")
        st.dataframe((fin / 1e6).round(0), width="stretch")
        if from_sec:
            st.caption(
                f"Source : SEC EDGAR, données XBRL déposées par {sec_data['name']} (CIK {sec_data['cik']}). "
                "Les trimestres sont reconstitués à partir des cumuls publiés (ex. T4 = année − 9 mois). "
                "Free cash flow = flux opérationnel − capex."
            )
            # Rapport d'où vient chaque colonne (celui du chiffre d'affaires, sinon du résultat net)
            src = sec_data["sources"]
            ref = next((r for r in ("Chiffre d'affaires", "Résultat net") if r in src.index), src.index[0])
            links = [
                {"Période": col, "Rapport source": sec.filing_url(sec_data["cik"], accn)}
                for col, accn in src.loc[ref].dropna().items()
            ]
            if links:
                with st.expander("🔗 Rapport SEC d'origine de chaque période"):
                    st.dataframe(
                        pd.DataFrame(links)[::-1], hide_index=True, width="stretch",
                        column_config={"Rapport source": st.column_config.LinkColumn(display_text="Ouvrir sur EDGAR")},
                    )
        else:
            st.caption("Source : Yahoo Finance, d'après les rapports publiés. Pour les sociétés américaines, préférez la source SEC EDGAR.")

    # --- Contrôle croisé Yahoo / SEC --------------------------------------- #
    if sec_data:
        yahoo = load_financials(ticker, quarterly)
        sec_tab = sec_data["table"]
        # Yahoo arrondit parfois la date de clôture à la fin du mois : tolérance de 10 jours
        pairs = []
        for s_col in sec_tab.columns:
            for y_col in yahoo.columns:
                if abs((pd.Timestamp(s_col) - pd.Timestamp(y_col)).days) <= 10:
                    pairs.append((s_col, y_col))
        if pairs:
            last, y_last = max(pairs)
            checks = []
            for label in ["Chiffre d'affaires", "Résultat opérationnel", "Résultat net", "Capex"]:
                if label in yahoo.index and label in sec_tab.index:
                    y, s = abs(yahoo.at[label, y_last]), abs(sec_tab.at[label, last])
                    if pd.notna(y) and pd.notna(s) and s:
                        gap = y / s - 1
                        checks.append({
                            "Poste": label, "Yahoo (M)": y / 1e6, "SEC (M)": s / 1e6,
                            "Écart (%)": gap * 100,
                            "Statut": "✅ cohérent" if abs(gap) < 0.02 else "⚠️ à vérifier",
                        })
            if checks:
                with st.expander(f"🔍 Contrôle croisé Yahoo / SEC (période close le {last})"):
                    st.dataframe(pd.DataFrame(checks).round(1), hide_index=True, width="stretch")
                    st.caption("Un écart signale une définition différente ou une erreur : la SEC fait foi.")

    # --- Rapports déposés ---------------------------------------------------- #
    if sec_data:
        try:
            reports = load_filings(ticker)
        except Exception:
            reports = pd.DataFrame()
        if not reports.empty:
            with st.expander("📄 Derniers rapports déposés à la SEC"):
                st.dataframe(
                    reports, hide_index=True, width="stretch",
                    column_config={"Lien": st.column_config.LinkColumn(display_text="Lire le rapport")},
                )

    if isinstance(row.get("longBusinessSummary"), str):
        with st.expander("Description de l'activité"):
            st.write(row["longBusinessSummary"])
