"""Univers d'entreprises suivis par le dashboard.

- S&P 500 : liste récupérée sur Wikipedia, mise en cache localement.
- Semi-conducteurs mondiaux et quantique : listes choisies à la main,
  avec les tickers Yahoo Finance de la place de cotation principale.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
SP500_CACHE = DATA_DIR / "sp500.csv"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# (ticker Yahoo, nom, segment de la chaîne de valeur)
SEMICONDUCTORS: list[tuple[str, str, str]] = [
    # États-Unis — conception (fabless) et fabricants intégrés
    ("NVDA", "NVIDIA", "Conception (GPU / IA)"),
    ("AVGO", "Broadcom", "Conception (réseau / ASIC)"),
    ("AMD", "AMD", "Conception (CPU / GPU)"),
    ("QCOM", "Qualcomm", "Conception (mobile)"),
    ("MRVL", "Marvell Technology", "Conception (data center)"),
    ("ARM", "Arm Holdings", "Propriété intellectuelle"),
    ("INTC", "Intel", "Fabricant intégré"),
    ("TXN", "Texas Instruments", "Analogique"),
    ("ADI", "Analog Devices", "Analogique"),
    ("MCHP", "Microchip Technology", "Microcontrôleurs"),
    ("ON", "onsemi", "Puissance / auto"),
    ("MU", "Micron Technology", "Mémoire"),
    ("GFS", "GlobalFoundries", "Fonderie"),
    # États-Unis — équipements et logiciels de conception
    ("AMAT", "Applied Materials", "Équipements"),
    ("LRCX", "Lam Research", "Équipements"),
    ("KLAC", "KLA", "Équipements (inspection)"),
    ("TER", "Teradyne", "Équipements (test)"),
    ("SNPS", "Synopsys", "Logiciels de conception"),
    ("CDNS", "Cadence Design Systems", "Logiciels de conception"),
    # Europe
    ("ASML.AS", "ASML", "Équipements (lithographie)"),
    ("ASM.AS", "ASM International", "Équipements"),
    ("BESI.AS", "BE Semiconductor", "Équipements (packaging)"),
    ("IFX.DE", "Infineon", "Puissance / auto"),
    ("STMPA.PA", "STMicroelectronics", "Fabricant intégré"),
    ("NXPI", "NXP Semiconductors", "Auto / IoT"),
    ("SOI.PA", "Soitec", "Matériaux (substrats)"),
    # Asie
    ("2330.TW", "TSMC", "Fonderie"),
    ("2454.TW", "MediaTek", "Conception (mobile)"),
    ("2303.TW", "UMC", "Fonderie"),
    ("3711.TW", "ASE Technology", "Packaging / test"),
    ("005930.KS", "Samsung Electronics", "Mémoire / fonderie"),
    ("000660.KS", "SK hynix", "Mémoire"),
    ("8035.T", "Tokyo Electron", "Équipements"),
    ("6857.T", "Advantest", "Équipements (test)"),
    ("6920.T", "Lasertec", "Équipements (inspection)"),
    ("6146.T", "Disco", "Équipements (découpe)"),
    ("6723.T", "Renesas Electronics", "Microcontrôleurs"),
    ("0981.HK", "SMIC", "Fonderie"),
]

QUANTUM: list[tuple[str, str, str]] = [
    # Acteurs « purs » du quantique
    ("IONQ", "IonQ", "Pur quantique (ions piégés)"),
    ("RGTI", "Rigetti Computing", "Pur quantique (supraconducteur)"),
    ("QBTS", "D-Wave Quantum", "Pur quantique (recuit)"),
    ("QUBT", "Quantum Computing Inc.", "Pur quantique (photonique)"),
    ("ARQQ", "Arqit Quantum", "Cryptographie post-quantique"),
    # Grands groupes avec un programme quantique important
    ("IBM", "IBM", "Grand groupe (programme quantique)"),
    ("GOOGL", "Alphabet", "Grand groupe (programme quantique)"),
    ("MSFT", "Microsoft", "Grand groupe (programme quantique)"),
    ("HON", "Honeywell (Quantinuum)", "Grand groupe (programme quantique)"),
    ("AMZN", "Amazon", "Grand groupe (programme quantique)"),
    ("NVDA", "NVIDIA", "Grand groupe (logiciel / simulation)"),
]


def _curated(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["ticker", "name", "segment"])


def load_sp500(max_age_days: int = 7) -> pd.DataFrame:
    """Retourne la composition du S&P 500 (ticker, nom, secteur, sous-secteur)."""
    fresh = (
        SP500_CACHE.exists()
        and time.time() - SP500_CACHE.stat().st_mtime < max_age_days * 86400
    )
    if not fresh:
        try:
            resp = requests.get(
                SP500_URL,
                headers={"User-Agent": "Mozilla/5.0 (stock-dashboard)"},
                timeout=20,
            )
            resp.raise_for_status()
            table = pd.read_html(io.StringIO(resp.text), attrs={"id": "constituents"})[0]
            df = pd.DataFrame(
                {
                    # Yahoo écrit BRK-B là où Wikipedia écrit BRK.B
                    "ticker": table["Symbol"].str.replace(".", "-", regex=False),
                    "name": table["Security"],
                    "segment": table["GICS Sector"],
                    "sub_industry": table["GICS Sub-Industry"],
                }
            )
            df.to_csv(SP500_CACHE, index=False)
        except Exception:
            if not SP500_CACHE.exists():
                raise
    return pd.read_csv(SP500_CACHE)


UNIVERSES = {
    "S&P 500": load_sp500,
    "Semi-conducteurs (monde)": lambda: _curated(SEMICONDUCTORS),
    "Quantique": lambda: _curated(QUANTUM),
}
