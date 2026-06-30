"""Scarto dei messaggi Telegram troppo vecchi (anti-segnale-stantio).

`python-telegram-bot` gestisce internamente le cadute di rete durante il polling e,
quando la connessione torna, **recupera** i messaggi accumulati offline. Per il
trading live un segnale vecchio di minuti è inutile/pericoloso (verrebbe scritto nel
CSV e ripiazzato). Questo modulo decide — in modo **puro e testabile** — se un
messaggio è troppo vecchio rispetto a "adesso", in base al suo timestamp (`msg.date`).
"""

import math

DEFAULT_MAX_AGE = 120  # secondi


def effective_max_age(max_signal_age, clear_delay):
    """`max_age` EFFETTIVO per il filtro freschezza, **non superiore a `clear_delay`** (#53):
    un messaggio già più vecchio della vita della riga CSV (`clear_delay`) verrebbe scritto e
    scadrebbe quasi subito → meglio trattarlo come stantio. Ritorna `min(max_signal_age,
    clear_delay)` quando entrambi sono numeri positivi finiti.

    Casi limite (sicurezza prima di tutto):
    - `clear_delay` malformato/non positivo → **nessun clamp** (si ritorna `max_signal_age`
      così com'è; `is_stale` applica comunque la sua coercizione difensiva);
    - `max_signal_age` esplicitamente `<= 0` (filtro disattivato dall'utente) → resta tale:
      il clamp NON deve **ri-attivare** un filtro che l'utente ha spento di proposito;
    - `max_signal_age` malformato → lasciato a `is_stale` (che ricade su `DEFAULT_MAX_AGE`)."""
    if isinstance(clear_delay, bool):
        return max_signal_age
    try:
        cd = float(clear_delay)
    except (TypeError, ValueError, OverflowError):
        return max_signal_age
    if not math.isfinite(cd) or cd <= 0:
        return max_signal_age
    if isinstance(max_signal_age, bool):
        return max_signal_age
    try:
        ma = float(max_signal_age)
    except (TypeError, ValueError, OverflowError):
        return max_signal_age
    if not math.isfinite(ma) or ma <= 0:
        return max_signal_age            # filtro disattivato dall'utente: non ri-attivarlo
    return min(ma, cd)


def is_stale(message_epoch, now, max_age=DEFAULT_MAX_AGE) -> bool:
    """`True` se il messaggio (epoch UNIX `message_epoch`) è più vecchio di `max_age`
    secondi rispetto a `now` (epoch UNIX).

    - `max_age` **coerciuto a float** in modo sicuro. Un valore **malformato** in config
      (``"abc"``/`bool`/`NaN`/`inf`/`None`/`Decimal` enorme) NON disattiva il filtro:
      il filtro è una protezione di sicurezza, quindi si torna al **default sicuro**
      (`DEFAULT_MAX_AGE`), così un `max_signal_age` corrotto non lascia passare un
      backlog vecchio dopo un reconnect (audit P1). Solo un numero **esplicitamente
      ``<= 0``** disattiva il filtro (scelta dell'utente, documentata in config).
      Una stringa numerica (es. ``"120"`` editata a mano) funziona come il numero.
      Niente eccezioni: un valore rotto al più ricade sul default, non crasha l'handler;
    - **`message_epoch` mancante/illeggibile → STALE (fail-CLOSED, audit A4)**: un messaggio
      di backlog recuperato senza data (`msg.date is None`) o con timestamp illeggibile NON
      deve bypassare l'anti-stale — sarebbe esattamente ciò che il modulo deve impedire.
      Viene quindi trattato come stantio e scartato;
    - **`now` illeggibile → non stantio (fail-OPEN)**: il `now` è il TUO clock; se è
      illeggibile meglio processare un segnale buono che scartarlo per un now rotto;
    - un messaggio dal **futuro** (clock skew) non è stantio.
    """
    # bool non è una soglia in secondi: un True/False trapelato da config ricade sul
    # default sicuro invece di valere 1/0 (che disattiverebbe il filtro per sbaglio).
    if isinstance(max_age, bool):
        max_age = DEFAULT_MAX_AGE
    else:
        try:
            max_age = float(max_age)
        except (TypeError, ValueError, OverflowError):
            max_age = DEFAULT_MAX_AGE    # None/"abc"/Decimal enorme → default (no crash)
        else:
            if not math.isfinite(max_age):
                max_age = DEFAULT_MAX_AGE  # NaN/inf → default sicuro
    if max_age <= 0:
        return False                 # solo un valore esplicito <= 0 disattiva il filtro
    # Timestamp del MESSAGGIO mancante/illeggibile → stantio (fail-closed, A4): un backlog
    # senza data non deve passare l'anti-stale.
    try:
        msg_epoch = float(message_epoch)
    except (TypeError, ValueError, OverflowError):
        return True
    if not math.isfinite(msg_epoch):
        return True                  # NaN/inf nel timestamp messaggio → stantio
    # `now` (il TUO clock) illeggibile → fail-open: non scartare un segnale buono.
    try:
        now_f = float(now)
    except (TypeError, ValueError, OverflowError):
        return False
    if not math.isfinite(now_f):
        return False
    return (now_f - msg_epoch) > max_age
