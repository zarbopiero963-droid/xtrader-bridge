"""Loader del dizionario XTrader (PR-07).

Il dizionario (`data/dizionario_xtrader.csv`) è il "traduttore" tra gli alias dei
segnali Telegram e i valori esatti che XTrader si aspetta (MarketType, MarketName,
SelectionName, Handicap, BetType). Basato sui dati reali forniti dal team XTrader.

PR-07 fornisce solo caricamento e validazione strutturale; il lookup vero e
proprio (alias → riga) e l'integrazione in `build_csv_row` sono PR-08.
"""

import csv
import os

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DIZIONARIO_PATH = os.path.join(_DATA_DIR, "dizionario_xtrader.csv")

EXPECTED_COLUMNS = [
    "Sport", "Periodo", "MarketAliasTelegram", "SelectionAliasTelegram",
    "MarketType_XTrader", "MarketName_XTrader", "SelectionRole",
    "SelectionName_XTrader", "Linea", "Handicap", "BetType_XTrader", "Lingua",
    "SelezioneDinamica", "MetodoConsigliato", "Stato", "Fonte",
    "EsempioEventName", "EsempioEventId", "EsempioMarketId",
    "EsempioSelectionId", "Note",
]


def load_dizionario(path: str = DIZIONARIO_PATH) -> list:
    """Carica il dizionario come lista di dict (una per riga)."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _norm(s: str) -> str:
    # minuscolo, trim e collasso degli spazi interni (es. "Over  0.5  HT" -> "over 0.5 ht").
    return " ".join(str(s).strip().lower().split())


def alias_key(market_alias: str, selection_alias: str) -> tuple:
    """Chiave normalizzata (case/space-insensitive) usata per il lookup (PR-08)."""
    return (_norm(market_alias), _norm(selection_alias))


def duplicate_alias_pairs(rows: list) -> list:
    """Coppie (MarketAliasTelegram, SelectionAliasTelegram) duplicate: devono
    essere zero, altrimenti il lookup sarebbe ambiguo. Le righe con alias vuoti
    vengono ignorate (non sono lookabili e non devono generare falsi duplicati)."""
    seen, dups = set(), []
    for row in rows:
        ma = str(row.get("MarketAliasTelegram", "")).strip()
        sa = str(row.get("SelectionAliasTelegram", "")).strip()
        if not ma or not sa:
            continue
        k = alias_key(ma, sa)
        if k in seen:
            dups.append(k)
        else:
            seen.add(k)
    return dups


def market_types(rows: list) -> set:
    return {row["MarketType_XTrader"] for row in rows}
