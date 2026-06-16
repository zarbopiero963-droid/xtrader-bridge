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


def alias_key(market_alias: str, selection_alias: str) -> tuple:
    """Chiave normalizzata (case/space-insensitive) usata per il lookup (PR-08)."""
    return (str(market_alias).strip().lower(), str(selection_alias).strip().lower())


def duplicate_alias_pairs(rows: list) -> list:
    """Coppie (MarketAliasTelegram, SelectionAliasTelegram) duplicate: devono
    essere zero, altrimenti il lookup sarebbe ambiguo."""
    seen, dups = set(), []
    for row in rows:
        k = alias_key(row["MarketAliasTelegram"], row["SelectionAliasTelegram"])
        if k in seen:
            dups.append(k)
        else:
            seen.add(k)
    return dups


def market_types(rows: list) -> set:
    return {row["MarketType_XTrader"] for row in rows}
