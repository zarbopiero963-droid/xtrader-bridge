"""Test della politica di riconnessione del listener (logica pura)."""

from xtrader_bridge import reconnect_policy as rp


# ── backoff ──────────────────────────────────────────────────────────────────

def test_backoff_cresce_esponenziale_dal_base():
    assert rp.backoff_delay(1) == 2.0      # base
    assert rp.backoff_delay(2) == 4.0
    assert rp.backoff_delay(3) == 8.0
    assert rp.backoff_delay(4) == 16.0


def test_backoff_limitato_al_cap():
    # Cresce ma non supera mai il tetto.
    assert rp.backoff_delay(100) == rp.DEFAULT_MAX_DELAY
    assert rp.backoff_delay(1, base=10, cap=25) == 10
    assert rp.backoff_delay(2, base=10, cap=25) == 20
    assert rp.backoff_delay(3, base=10, cap=25) == 25   # 40 → cap 25


def test_backoff_attempt_non_valido_trattato_come_primo():
    assert rp.backoff_delay(0) == 2.0
    assert rp.backoff_delay(-5) == 2.0


# ── classificazione errori (whitelist transitori) ────────────────────────────

class NetworkError(Exception):
    pass


class TimedOut(NetworkError):
    pass


class RetryAfter(Exception):
    pass


class InvalidToken(Exception):
    pass


def test_errori_di_rete_sono_transitori():
    assert rp.is_transient_error(NetworkError("giù")) is True
    assert rp.is_transient_error(TimedOut("timeout")) is True      # via MRO (sottoclasse)
    assert rp.is_transient_error(RetryAfter("flood")) is True


def test_errori_permanenti_e_inattesi_non_sono_transitori():
    # Token invalido = configurazione sbagliata: NON deve ciclare a vuoto.
    assert rp.is_transient_error(InvalidToken("token")) is False
    # Un errore inatteso (bug) non è in whitelist → niente retry infinito.
    assert rp.is_transient_error(ValueError("bug")) is False
    assert rp.is_transient_error(RuntimeError("boom")) is False


# ── decisione finale del supervisor ──────────────────────────────────────────

def test_should_reconnect_solo_se_running_e_transitorio():
    # Errore di rete mentre il bridge è attivo → riconnetti.
    assert rp.should_reconnect(True, NetworkError("x")) is True
    # STOP manuale (running=False) → mai, nemmeno su errore di rete.
    assert rp.should_reconnect(False, NetworkError("x")) is False
    # Errore permanente, anche se attivo → no.
    assert rp.should_reconnect(True, InvalidToken("x")) is False
