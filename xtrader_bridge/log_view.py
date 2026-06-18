"""PR-14b: filtro del log per livello per la GUI (logica pura, testabile in CI).

La GUI tiene in memoria le righe del log già formattate da `event_log.format_entry`
(`[HH:MM:SS] [LEVEL] messaggio`) e mostra solo quelle del livello selezionato in un
menu a tendina. Qui vive SOLO la logica di selezione: la voce "Tutti" (mostra tutto)
e i livelli noti, delegando il filtro per livello a `event_log.filter_by_level`
(che legge il campo header strutturale, non il testo). Nessun widget.
"""

from . import event_log

# Voce del menu "mostra tutto" (non è un livello di log).
ALL = "Tutti"
# Opzioni del menu a tendina, nell'ordine: Tutti + i livelli di event_log
# (fonte UNICA dei livelli → niente disallineamento con classify/format_entry).
OPTIONS = (ALL,) + event_log.LEVELS


def filter_lines(lines, selected) -> list:
    """Righe da mostrare dato il valore selezionato nel menu.

    `ALL` (o un valore non riconosciuto) → **tutte** le righe; un livello noto
    (INFO/WARNING/ERROR/SIGNAL) → solo le righe di quel livello. Ritorna sempre una
    nuova lista (non muta l'input)."""
    sel = str(selected or "").strip()
    if sel not in event_log.LEVELS:      # ALL o valore ignoto → nessun filtro
        return list(lines)
    return event_log.filter_by_level(lines, sel)
