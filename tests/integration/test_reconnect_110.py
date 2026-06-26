"""Test hard del ciclo di vita del listener (issue #110) — METODI REALI di `App`.

#110 è un secondo "Codex resilience/crash-recovery test plan", in larga parte
sovrapposto a #109: quasi tutta la "lista finale" è già coperta da #160/#161/#162
(drop_pending_updates, stale update, epoch/no-doppio-poller, rollback _process,
confirmation write-failure, manual-clear active-path, gate _running, daily atomico).

Qui si chiudono i due gap automatizzabili rimasti, sul supervisor `App._run_bot`:
- #110/6 — errore TRANSITORIO durante il polling → `_safe_shutdown_tg` (chiusura del
  vecchio updater, niente doppio poller) → attesa di backoff → RITENTA → alla
  riconnessione riuscita `_reconnect_attempt` torna a 0;
- #110/7 — STOP durante il backoff interrompe SUBITO l'attesa (`_reconnect_wait`
  sblocca su `_stop_event`, niente busy-wait di 60s).

La classificazione transitorio/permanente è testata a parte (`test_reconnect_policy.py`):
qui `should_reconnect` è forzato per pilotare DETERMINISTICAMENTE il ramo di retry,
indipendentemente da `python-telegram-bot` (presente o meno nell'ambiente).
"""

import threading
import time


class _Updater:
    def __init__(self, on_poll):
        self._on_poll = on_poll

    async def start_polling(self, **kwargs):
        self._on_poll()        # alla connessione riuscita fa uscire il supervisor

    async def stop(self):
        pass


class _TgApp:
    def __init__(self, *, fail, on_poll):
        self.updater = _Updater(on_poll)
        self._fail = fail

    def add_handler(self, h):
        pass

    async def initialize(self):
        if self._fail:
            # nome "NetworkError" = errore transitorio (la decisione è comunque
            # forzata via should_reconnect nel test → deterministico in ogni ambiente).
            raise type("NetworkError", (Exception,), {})("rete giù (simulato)")

    async def start(self):
        pass

    async def stop(self):
        pass

    async def shutdown(self):
        pass


def test_reconnect_lifecycle_errore_transitorio_ritenta_e_resetta(make_app, app_mod, monkeypatch):
    a = make_app()
    a._running = True
    a._listener_epoch = 3
    a._reconnect_attempt = 0
    # forza il ramo "transitorio → riconnetti" (classificazione testata altrove)
    monkeypatch.setattr(app_mod.reconnect_policy, "should_reconnect", lambda running, exc: True)
    waits = []
    a._reconnect_wait = lambda delay: waits.append(delay)     # niente sleep reale nel test
    shutdowns = []
    a._safe_shutdown_tg = lambda: shutdowns.append(True)

    builds = {"n": 0}

    def _factory():
        builds["n"] += 1
        fail = builds["n"] == 1          # 1ª connessione fallisce, 2ª riesce

        def _on_poll():
            a._running = False           # connessione riuscita: esci dal supervisor

        class _B:
            def token(self, _t):
                return self

            def build(self):
                return _TgApp(fail=fail, on_poll=_on_poll)
        return _B()

    monkeypatch.setattr(app_mod, "ApplicationBuilder", _factory)
    monkeypatch.setattr(app_mod, "MessageHandler", lambda *a_, **k: ("MH", a_, k))

    app_mod.App._run_bot(a, {"bot_token": "x"}, 3)

    assert builds["n"] == 2                 # ha ritentato dopo l'errore transitorio
    assert shutdowns == [True]              # vecchio updater chiuso PRIMA del retry (no doppio poller)
    assert len(waits) == 1 and waits[0] > 0  # ha atteso il backoff una volta
    assert a._reconnect_attempt == 0         # reset dopo la riconnessione riuscita


def test_stop_durante_backoff_interrompe_subito(make_app, app_mod):
    a = make_app()
    a._stop_event = threading.Event()
    a._stop_event.set()                    # STOP già avvenuto durante l'attesa

    t0 = time.monotonic()
    app_mod.App._reconnect_wait(a, 30.0)   # NON deve dormire 30s
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0                    # lo STOP sblocca subito il backoff
