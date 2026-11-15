"""Récupération des données (Yahoo Finance via yfinance) avec cache disque.

Les montants sont convertis en dollars US pour pouvoir comparer des
entreprises cotées dans des devises différentes.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
INFO_TTL = 24 * 3600  # une journée : les fondamentaux bougent peu

INFO_FIELDS = [
    "longName", "country", "sector", "industry", "currency", "financialCurrency",
    "marketCap", "totalRevenue", "revenueGrowth", "grossMargins",
    "operatingMargins", "profitMargins", "trailingPE", "forwardPE",
    "priceToSalesTrailing12Months", "enterpriseToEbitda", "freeCashflow",
    "totalCash", "totalDebt", "returnOnEquity", "dividendYield", "beta",
    "currentPrice", "longBusinessSummary", "website",
]


# --------------------------------------------------------------------------- #
# Devises
# --------------------------------------------------------------------------- #
def _fx_to_usd(currency: str | None, rates: dict[str, float]) -> float | None:
    """Combien de dollars vaut une unité de `currency`."""
    if not currency:
        return None
    if currency == "USD":
        return 1.0
    # Les cotations de Londres en pence (GBp) valent 1/100 de livre
    if currency in ("GBp", "GBX"):
        base = rates.get("GBP")
        return base / 100 if base else None
    return rates.get(currency.upper())


def fetch_fx_rates(currencies: set[str]) -> dict[str, float]:
    wanted = {
        ("GBP" if c in ("GBp", "GBX") else c.upper())
        for c in currencies
        if c and c != "USD"
    }
    rates: dict[str, float] = {}
    for cur in wanted:
        try:
            hist = yf.Ticker(f"{cur}USD=X").history(period="5d")
            if not hist.empty:
                rates[cur] = float(hist["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return rates


# --------------------------------------------------------------------------- #
# Fiches entreprises (fondamentaux)
# --------------------------------------------------------------------------- #
def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"info_{ticker.replace('/', '_')}.json"


def fetch_info(ticker: str, force: bool = False) -> dict:
    path = _cache_path(ticker)
    if not force and path.exists() and time.time() - path.stat().st_mtime < INFO_TTL:
        return json.loads(path.read_text(encoding="utf-8"))
    info: dict = {}
    for attempt in range(3):
        try:
            raw = yf.Ticker(ticker).info or {}
            info = {k: raw.get(k) for k in INFO_FIELDS}
            break
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    info["ticker"] = ticker
    if info.get("marketCap") or info.get("longName"):
        path.write_text(json.dumps(info), encoding="utf-8")
    return info


def fetch_infos(tickers: list[str], progress=None, workers: int = 4) -> list[dict]:
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, info in enumerate(pool.map(fetch_info, tickers), start=1):
            results.append(info)
            if progress:
                progress(i / len(tickers), f"{i}/{len(tickers)} entreprises chargées")
    return results


# --------------------------------------------------------------------------- #
# Cours de bourse
# --------------------------------------------------------------------------- #
def fetch_prices(tickers: list[str], period: str = "2y") -> pd.DataFrame:
    """Cours de clôture ajustés, une colonne par ticker (devise locale)."""
    data = yf.download(
        tickers, period=period, auto_adjust=True, progress=False,
        threads=True, group_by="column",
    )
    if data.empty:
        return pd.DataFrame()
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    return close


def performance(close: pd.DataFrame) -> pd.DataFrame:
    """Performances 1 mois, depuis le 1er janvier et 1 an, en devise locale."""
    out = {}
    if close.empty:
        return pd.DataFrame(columns=["perf_1m", "perf_ytd", "perf_1y"])
    last_date = close.index.max()
    year_start = close[close.index >= pd.Timestamp(year=last_date.year, month=1, day=1)]
    for col in close.columns:
        s = close[col].dropna()
        if s.empty:
            continue
        last = s.iloc[-1]

        def ago(days: int) -> float | None:
            past = s[s.index <= last_date - pd.Timedelta(days=days)]
            return last / past.iloc[-1] - 1 if not past.empty else None

        ytd_base = year_start[col].dropna()
        out[col] = {
            "perf_1m": ago(30),
            "perf_ytd": last / ytd_base.iloc[0] - 1 if not ytd_base.empty else None,
            "perf_1y": ago(365),
        }
    return pd.DataFrame.from_dict(out, orient="index")


# --------------------------------------------------------------------------- #
# Tableau comparatif d'un univers
# --------------------------------------------------------------------------- #
def build_screener(universe: pd.DataFrame, progress=None) -> pd.DataFrame:
    tickers = universe["ticker"].tolist()
    infos = pd.DataFrame(fetch_infos(tickers, progress=progress)).set_index("ticker")

    rates = fetch_fx_rates(
        set(infos.get("currency", pd.Series(dtype=str)).dropna())
        | set(infos.get("financialCurrency", pd.Series(dtype=str)).dropna())
    )
    quote_fx = infos["currency"].map(lambda c: _fx_to_usd(c, rates))
    fin_fx = infos["financialCurrency"].fillna(infos["currency"]).map(
        lambda c: _fx_to_usd(c, rates)
    )

    df = universe.set_index("ticker").join(infos, how="left")
    df["market_cap_usd"] = df["marketCap"] * quote_fx
    df["revenue_usd"] = df["totalRevenue"] * fin_fx
    df["fcf_usd"] = df["freeCashflow"] * fin_fx
    df["net_cash_usd"] = (df["totalCash"].fillna(0) - df["totalDebt"].fillna(0)) * fin_fx
    df["fcf_yield"] = df["fcf_usd"] / df["market_cap_usd"]

    perf = performance(fetch_prices(tickers, period="2y"))
    df = df.join(perf, how="left")
    return df.reset_index()


# --------------------------------------------------------------------------- #
# Fiche détaillée d'une entreprise
# --------------------------------------------------------------------------- #
ROWS = {
    "Chiffre d'affaires": ("income", ["Total Revenue", "Operating Revenue"]),
    "Marge brute": ("income", ["Gross Profit"]),
    "Résultat opérationnel": ("income", ["Operating Income", "Total Operating Income As Reported"]),
    "Résultat net": ("income", ["Net Income", "Net Income Common Stockholders"]),
    "R&D": ("income", ["Research And Development"]),
    "Flux de trésorerie opérationnel": ("cash", ["Operating Cash Flow"]),
    "Capex": ("cash", ["Capital Expenditure"]),
    "Free cash flow": ("cash", ["Free Cash Flow"]),
    "Amortissements (D&A)": ("cash", ["Depreciation And Amortization", "Depreciation Amortization Depletion"]),
    "Rémunération en actions (SBC)": ("cash", ["Stock Based Compensation"]),
    "Rachats d'actions": ("cash", ["Repurchase Of Capital Stock"]),
}


def _pick(frame: pd.DataFrame, names: list[str]) -> pd.Series | None:
    for n in names:
        if n in frame.index:
            return frame.loc[n]
    return None


def financials(ticker: str, quarterly: bool = True) -> pd.DataFrame:
    """Lignes clés du compte de résultat et des flux de trésorerie.

    Colonnes = périodes (de la plus ancienne à la plus récente), en devise de
    publication de l'entreprise.
    """
    t = yf.Ticker(ticker)
    income = t.quarterly_income_stmt if quarterly else t.income_stmt
    cash = t.quarterly_cashflow if quarterly else t.cashflow
    frames = {"income": income, "cash": cash}
    rows = {}
    for label, (kind, names) in ROWS.items():
        frame = frames[kind]
        if frame is None or frame.empty:
            continue
        s = _pick(frame, names)
        if s is not None:
            rows[label] = s
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).T
    df = df[sorted(df.columns)]
    df.columns = [c.strftime("%Y-%m-%d") for c in df.columns]
    # On écarte les périodes où presque tout est vide (Yahoo en ajoute parfois)
    df = df.loc[:, df.notna().sum() >= max(2, len(df) // 3)]
    return df
