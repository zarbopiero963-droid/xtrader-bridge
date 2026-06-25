"""Mappatura PURA degli esiti guardrail non-WRITE → presentazione.

Estratto da `App._after_non_write` (#136 item 1, refactor incrementale di `app.py`):
la traduzione di una decisione `live_guard` (DRY_RUN / DUPLICATE / RATE_LIMITED /
DAILY_LIMITED) nel testo di log, nel contatore della dashboard e nell'eventuale
aggiornamento «ultimo segnale» è qui, testabile headless.

`App` applica il risultato via GUI (`_bump` / `_log` / `_set_last`): qui dentro NON si
tocca tkinter e non si scrive nulla. Un esito di SCRITTURA (`live_guard.WRITE`) non
passa da qui — ha il suo percorso in `_process`.
"""

from . import live_guard


class NonWriteOutcome:
    """Descrizione di presentazione per un esito che NON scrive il CSV.

    - `counter`: nome del contatore della dashboard da incrementare (`_bump`);
    - `log`: riga di log da mostrare (`_log`);
    - `last_signal`: testo «ultimo segnale» (`_set_last`), oppure `None` se l'esito
      non aggiorna l'ultimo segnale (solo DRY_RUN lo fa);
    - `last_color`: colore per «ultimo segnale» (significativo solo se `last_signal`).
    """

    __slots__ = ("counter", "log", "last_signal", "last_color")

    def __init__(self, counter, log, last_signal=None, last_color=None):
        self.counter = counter
        self.log = log
        self.last_signal = last_signal
        self.last_color = last_color


def describe_non_write(decision, row):
    """Ritorna la `NonWriteOutcome` per `decision`, o `None` se non è un esito
    non-WRITE noto (il chiamante non fa nulla, come prima dell'estrazione).

    `row` è la riga CSV parsata: si leggono solo `EventName`/`SelectionName`/`Price`
    (campi mancanti → stringa vuota), nessuna mutazione."""
    ev = row.get("EventName", "")
    sel = row.get("SelectionName", "")
    price = row.get("Price", "")
    if decision == live_guard.DRY_RUN:
        return NonWriteOutcome(
            counter="dry_run",
            log=f"🧪 DRY_RUN: segnale riconosciuto ma CSV NON scritto (simulazione): "
                f"{ev} | {sel}",
            last_signal=f"🧪 DRY_RUN — {ev}  |  {sel}  q.{price}",
            last_color="#ffb74d",
        )
    if decision == live_guard.DUPLICATE:
        return NonWriteOutcome(
            counter="duplicate",
            log=f"♻️ Duplicato ignorato (nessuna doppia scommessa): {ev} | {sel}",
        )
    if decision == live_guard.RATE_LIMITED:
        return NonWriteOutcome(
            counter="limited",
            log="🚦 Limite al minuto raggiunto: segnale ignorato.",
        )
    if decision == live_guard.DAILY_LIMITED:
        return NonWriteOutcome(
            counter="limited",
            log="🚦 Limite giornaliero raggiunto: segnale ignorato.",
        )
    return None


class WriteOutcome:
    """Descrizione di presentazione per una scrittura CSV RIUSCITA.

    - `last_signal`: testo «ultimo segnale» (bianco) da `_set_last`;
    - `signal_log`: riga di log del segnale scritto (con la sorgente del parser);
    - `csv_log`: riga di log di conferma aggiornamento CSV (pluralizzazione
      «attivo»/«attivi» secondo il numero di righe attive).
    """

    __slots__ = ("last_signal", "signal_log", "csv_log")

    def __init__(self, last_signal, signal_log, csv_log):
        self.last_signal = last_signal
        self.signal_log = signal_log
        self.csv_log = csv_log


def describe_write(row, source, n_active):
    """Presentazione di una scrittura CSV riuscita per `row` (riga parsata),
    `source` (sorgente del parser) e `n_active` (righe attive nel CSV dopo la
    scrittura). Pura: legge solo `EventName`/`SelectionName`/`Price` (mancanti →
    stringa vuota), nessuna mutazione."""
    ev = row.get("EventName", "")
    sel = row.get("SelectionName", "")
    price = row.get("Price", "")
    plural = "o" if n_active == 1 else "i"
    return WriteOutcome(
        last_signal=f"🏆 {ev}  |  {sel}  |  q.{price}",
        signal_log=f"📱 Segnale ({source}): {ev}  |  {sel}  q.{price}",
        csv_log=f"✅ CSV aggiornato ({n_active} attiv{plural}) → XTrader può piazzare",
    )
