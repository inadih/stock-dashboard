"""Chiffres officiels déposés auprès de la SEC (EDGAR, données XBRL).

- Trouve l'identifiant SEC (CIK) d'une entreprise à partir de son ticker.
- Récupère les faits XBRL (chiffre d'affaires, résultat, capex…) des
  rapports 10-Q / 10-K (sociétés américaines) ou 20-F (sociétés étrangères
  cotées aux États-Unis via des ADR).
- Reconstitue des trimestres « purs » : les flux de trésorerie des 10-Q sont
  publiés en cumul depuis le début de l'exercice, et le 4e trimestre n'existe
  que via le rapport annuel (année − 9 mois).
- Garde, pour chaque chiffre, le rapport d'où il vient (lien EDGAR).

La SEC demande un User-Agent identifiable. Vous pouvez définir le vôtre
avec la variable d'environnement SEC_USER_AGENT (ex. « Prénom Nom email »).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(__file__).parent / "data" / "sec"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CIK_CACHE = CACHE_DIR / "cik.json"
TTL = 24 * 3600

HEADERS = {
    "User-Agent": os.environ.get("SEC_USER_AGENT", "stock-dashboard/1.0 personal research tool"),
    "Accept-Encoding": "gzip, deflate",
}

# Sociétés cotées hors des États-Unis dont les ADR déposent des rapports à la SEC
SEC_TICKER_OVERRIDE = {
    "2330.TW": "TSM",
    "ASML.AS": "ASML",
    "2303.TW": "UMC",
    "3711.TW": "ASX",
    "STMPA.PA": "STM",
}

# Libellé → concepts XBRL acceptés, par ordre de préférence (US GAAP puis IFRS)
CONCEPTS: dict[str, list[str]] = {
    "Chiffre d'affaires": [
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet", "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers",
    ],
    "Marge brute": ["us-gaap:GrossProfit", "ifrs-full:GrossProfit"],
    "Résultat opérationnel": ["us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"],
    "Résultat net": [
        "us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss",
        "ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss",
    ],
    "R&D": [
        "us-gaap:ResearchAndDevelopmentExpense",
        "us-gaap:ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ifrs-full:ResearchAndDevelopmentExpense",
    ],
    "Flux de trésorerie opérationnel": [
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    ],
    "Capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    ],
    "Amortissements (D&A)": [
        "us-gaap:DepreciationDepletionAndAmortization", "us-gaap:DepreciationAndAmortization",
        "us-gaap:DepreciationAmortizationAndAccretionNet", "us-gaap:Depreciation",
        "ifrs-full:DepreciationAndAmortisationExpense",
    ],
    "Rémunération en actions (SBC)": [
        "us-gaap:ShareBasedCompensation", "us-gaap:AllocatedShareBasedCompensationExpense",
    ],
    "Rachats d'actions": ["us-gaap:PaymentsForRepurchaseOfCommonStock"],
    # Postes de bilan (valeurs à une date, pas sur une période)
    "Trésorerie": [
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "ifrs-full:CashAndCashEquivalents",
    ],
    "Dette long terme": [
        "us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt",
        "ifrs-full:NoncurrentFinancialLiabilities",
    ],
    "Capitaux propres": [
        "us-gaap:StockholdersEquity",
        "ifrs-full:EquityAttributableToOwnersOfParent", "ifrs-full:Equity",
    ],
}
INSTANT = {"Trésorerie", "Dette long terme", "Capitaux propres"}
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "20-F/A", "40-F", "10-KT"}


# --------------------------------------------------------------------------- #
# Accès réseau avec cache disque
# --------------------------------------------------------------------------- #
def _get_json(url: str, cache: Path | None = None, params: dict | None = None) -> dict:
    if cache and cache.exists() and time.time() - cache.stat().st_mtime < TTL:
        return json.loads(cache.read_text(encoding="utf-8"))
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    time.sleep(0.12)  # la SEC limite à 10 requêtes par seconde
    if cache:
        cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def sec_ticker(ticker: str) -> str | None:
    """Ticker sous lequel l'entreprise est connue à la SEC (None si non coté aux US)."""
    if ticker in SEC_TICKER_OVERRIDE:
        return SEC_TICKER_OVERRIDE[ticker]
    return None if "." in ticker else ticker  # suffixe .AS, .T, .KS… = cotation locale


def find_cik(ticker: str) -> int | None:
    t = sec_ticker(ticker)
    if not t:
        return None
    known = json.loads(CIK_CACHE.read_text(encoding="utf-8")) if CIK_CACHE.exists() else {}
    if t in known:
        return known[t]
    res = _get_json("https://efts.sec.gov/LATEST/search-index", params={"keysTyped": t})
    cik = None
    for hit in res.get("hits", {}).get("hits", []):
        tickers = [x.strip().upper() for x in hit["_source"].get("tickers", "").split(",")]
        if t.upper() in tickers:
            cik = int(hit["_id"])
            break
    known[t] = cik
    CIK_CACHE.write_text(json.dumps(known), encoding="utf-8")
    return cik


def filing_url(cik: int, accn: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{accn}-index.htm"


# --------------------------------------------------------------------------- #
# Faits XBRL → séries trimestrielles et annuelles
# --------------------------------------------------------------------------- #
def _facts(cik: int) -> dict:
    return _get_json(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        cache=CACHE_DIR / f"facts_{cik}.json",
    )


def _main_currency(facts: dict) -> str | None:
    """Devise de publication : l'unité monétaire la plus fréquente dans le dépôt."""
    counts: dict[str, int] = {}
    for ns in facts.get("facts", {}).values():
        for node in ns.values():
            for unit, rows in node.get("units", {}).items():
                if len(unit) == 3 and unit.isupper():  # codes ISO : USD, EUR, TWD…
                    counts[unit] = counts.get(unit, 0) + len(rows)
    return max(counts, key=counts.get) if counts else None


def _concept_rows(facts: dict, concept: str, unit: str | None) -> pd.DataFrame:
    ns, name = concept.split(":")
    node = facts.get("facts", {}).get(ns, {}).get(name)
    if not node or unit not in node["units"]:
        return pd.DataFrame()
    df = pd.DataFrame(node["units"][unit])
    df = df[df["form"].isin(FORMS)]
    if df.empty:
        return df
    df["end"] = pd.to_datetime(df["end"])
    if "start" in df:
        df["start"] = pd.to_datetime(df["start"])
    # Une même période apparaît dans plusieurs rapports : on garde le plus récent
    keys = ["start", "end"] if "start" in df else ["end"]
    return df.sort_values("filed").drop_duplicates(keys, keep="last")


def _discrete(df: pd.DataFrame) -> tuple[dict, dict]:
    """Retourne ({fin de trimestre: (valeur, n° de rapport)}, {fin d'année: (valeur, rapport)})."""
    quarters: dict = {}
    annual: dict = {}
    df = df.assign(days=(df["end"] - df["start"]).dt.days)
    for r in df.itertuples():
        if 80 <= r.days <= 100:
            quarters[r.end] = (r.val, r.accn)
        elif 350 <= r.days <= 380:
            annual[r.end] = (r.val, r.accn)
    # Trimestres déduits des cumuls depuis le début de l'exercice
    for _, grp in df.groupby("start"):
        grp = grp.sort_values("end")
        prev = None
        for r in grp.itertuples():
            if prev is not None and r.end not in quarters:
                gap = (r.end - prev.end).days
                if 80 <= gap <= 100:
                    quarters[r.end] = (r.val - prev.val, r.accn)
            prev = r
    return quarters, annual


def statements(ticker: str, quarterly: bool = True, periods: int = 12) -> dict | None:
    """Comptes officiels SEC.

    Retourne {"table": DataFrame (lignes = postes, colonnes = dates de fin),
              "sources": DataFrame (mêmes dimensions, n° de rapport),
              "currency": devise, "cik": CIK, "name": nom déposé}
    ou None si l'entreprise ne dépose pas à la SEC.
    """
    cik = find_cik(ticker)
    if not cik:
        return None
    facts = _facts(cik)
    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    currency = _main_currency(facts)
    for label, concepts in CONCEPTS.items():
        merged: dict = {}
        for concept in concepts:
            df = _concept_rows(facts, concept, currency)
            if df.empty:
                continue
            if label in INSTANT:
                series = {r.end: (r.val, r.accn) for r in df.itertuples()}
            else:
                if "start" not in df:
                    continue
                q, a = _discrete(df)
                series = q if quarterly else a
            for end, v in series.items():
                merged.setdefault(end, v)  # le concept prioritaire l'emporte
        if merged:
            values[label] = {k: v[0] for k, v in merged.items()}
            sources[label] = {k: v[1] for k, v in merged.items()}
    if not values:
        return None

    table = pd.DataFrame(values).T
    src = pd.DataFrame(sources).T
    # Colonnes de référence = périodes où le chiffre d'affaires ou le résultat existe
    anchor = next((l for l in ("Chiffre d'affaires", "Résultat net", "Résultat opérationnel") if l in table.index), None)
    cols = table.loc[anchor].dropna().index if anchor else table.columns
    cols = sorted(cols)[-periods:]
    table, src = table.reindex(columns=cols), src.reindex(columns=cols)
    table.columns = src.columns = [c.strftime("%Y-%m-%d") for c in cols]
    return {
        "table": table, "sources": src, "currency": currency,
        "cik": cik, "name": facts.get("entityName", ticker),
    }


def filings(ticker: str, limit: int = 12) -> pd.DataFrame:
    """Derniers rapports périodiques déposés (10-K, 10-Q, 20-F…) avec leur lien."""
    cik = find_cik(ticker)
    if not cik:
        return pd.DataFrame()
    sub = _get_json(
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
        cache=CACHE_DIR / f"submissions_{cik}.json",
    )
    recent = pd.DataFrame(sub.get("filings", {}).get("recent", {}))
    if recent.empty:
        return recent
    keep = recent[recent["form"].isin(FORMS)].head(limit)
    keep = keep.assign(
        url=[
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{a.replace('-', '')}/{d}"
            for a, d in zip(keep["accessionNumber"], keep["primaryDocument"])
        ]
    )
    return keep[["form", "reportDate", "filingDate", "url"]].rename(
        columns={"form": "Type", "reportDate": "Période", "filingDate": "Déposé le", "url": "Lien"}
    )
