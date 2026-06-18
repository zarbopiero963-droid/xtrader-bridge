"""Politica di riconnessione del listener Telegram (logica pura, testabile in CI).

Il listener gira in un thread (`app._run_bot`). Se la connessione cade, vogliamo
**riprovare** con un ritardo crescente (backoff) finché il bridge è in esecuzione,
SENZA:
- ritentare dopo uno STOP manuale (è una chiusura voluta);
- ritentare all'infinito su un errore **permanente** (es. token invalido), che non
  si risolve da solo e farebbe girare a vuoto.

Qui sta solo la **decisione** (quanto aspettare, se ritentare): nessun widget, nessun
asyncio, nessuna dipendenza da `python-telegram-bot`. Così è interamente testabile.
La parte di I/O (ricostruire l'updater, attendere) vive nella vista sottile `app`.
"""

# Backoff esponenziale, in secondi: 2, 4, 8, 16, 32, … limitato a un tetto.
DEFAULT_BASE_DELAY = 2.0
DEFAULT_MAX_DELAY = 60.0

# Errori considerati **transitori** (rete/timeout): vale la pena riprovare. Match per
# NOME di classe lungo l'intera gerarchia (MRO), così non serve importare telegram e
# il test può usare classi finte con questi nomi. Tutto ciò che NON è in whitelist è
# trattato come NON recuperabile (token invalido, bug, auth…) → niente retry: meglio
# fermarsi e mostrare l'errore che ciclare a vuoto.
TRANSIENT_ERROR_NAMES = frozenset({
    "NetworkError",      # telegram.error.NetworkError (base dei problemi di rete)
    "TimedOut",          # telegram.error.TimedOut
    "RetryAfter",        # flood control: riprovare più tardi
})


def backoff_delay(attempt: int, base: float = DEFAULT_BASE_DELAY,
                  cap: float = DEFAULT_MAX_DELAY) -> float:
    """Ritardo (secondi) prima del tentativo di riconnessione `attempt` (1-based).

    `attempt=1 → base`, poi raddoppia ad ogni tentativo, limitato a `cap`. Valori
    `attempt < 1` sono trattati come 1 (mai un ritardo negativo o nullo)."""
    if attempt < 1:
        attempt = 1
    delay = base * (2 ** (attempt - 1))
    return float(min(delay, cap))


def is_transient_error(exc: BaseException) -> bool:
    """`True` se l'eccezione è un errore transitorio noto (rete/timeout) per cui ha
    senso riconnettersi. Riconosce i tipi per nome lungo tutta la gerarchia, così un
    `TimedOut(NetworkError)` è transitorio mentre `InvalidToken`/`ValueError` no."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    return bool(names & TRANSIENT_ERROR_NAMES)


def should_reconnect(running: bool, exc: BaseException) -> bool:
    """Decisione finale del supervisor: riconnettersi solo se il bridge è ancora in
    esecuzione (uno STOP manuale azzera `running` → nessun retry) **e** l'errore è
    transitorio. Un errore permanente o una chiusura voluta non vanno ritentati."""
    return bool(running) and is_transient_error(exc)
