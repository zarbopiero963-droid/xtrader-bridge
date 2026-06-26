"""Harness per testare la GLUE runtime di `app.py` HEADLESS (issue #108 P1).

`app.py` importa `customtkinter`/`tkinter`/`telegram`, assenti in CI: per questo la
glue runtime safety-critical (`_process`, `_stop`, `_expire_tick`,
`_process_confirmation`, `_manual_clear` e il dispatch del listener) era dichiarata
«non testabile in CI» e verificata solo a mano su Windows (vedi docstring di
`tests/integration/test_confirmation_flow.py`). È IL buco principale segnalato
dall'audit #108.

Qui la rendiamo testabile installando STUB minimi di quei moduli in `sys.modules`
PRIMA di importare `app`, con `ctk.CTk = object` così la classe `App` è
sottoclassabile e istanziabile via `object.__new__` SENZA avviare Tk. I test
esercitano i **metodi reali** di `App` (non reimplementazioni): l'unico contorno
simulato è la GUI (sink no-op / cattura) e, dove serve iniettare un guasto,
`write_rows`/`resolve_row`/`should_process`. La logica safety-critical sotto test
(lock, coda, dedupe, daily, rollback, scrittura/svuotamento CSV, scadenza, gate
`_running`, dispatch listener) è quella vera del progetto.

Gli stub si installano solo se i moduli reali sono assenti: su un ambiente con Tk
reale (Windows) i test usano comunque `object.__new__` + sink shadowati, quindi non
aprono finestre.
"""

import sys
import threading
import types
from unittest.mock import MagicMock

import pytest


def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    # PEP 562: ogni attributo non definito esplicitamente → MagicMock (i widget
    # CTk* servono solo dentro _build_ui, mai a import-time né nei test della glue).
    mod.__getattr__ = lambda n: MagicMock()
    return mod


def _install_gui_stubs():
    if "customtkinter" not in sys.modules:
        sys.modules["customtkinter"] = _stub_module(
            "customtkinter",
            CTk=object,                                   # base class REALE, sottoclassabile
            set_appearance_mode=lambda *a, **k: None,
            set_default_color_theme=lambda *a, **k: None,
        )
    if "tkinter" not in sys.modules:
        sys.modules["tkinter"] = _stub_module("tkinter")
        sys.modules["tkinter.messagebox"] = _stub_module("tkinter.messagebox")
    if "telegram" not in sys.modules:
        sys.modules["telegram"] = _stub_module("telegram", Update=object)
        sys.modules["telegram.ext"] = _stub_module(
            "telegram.ext",
            ApplicationBuilder=MagicMock,
            MessageHandler=lambda *a, **k: ("MessageHandler", a, k),
            ContextTypes=MagicMock(),
        )


_install_gui_stubs()
import xtrader_bridge.app as _app_mod  # noqa: E402  (deve seguire l'install degli stub)


class _Widget:
    """Stand-in di un widget CTk: `.configure(...)` no-op (usato da `_stop`)."""

    def configure(self, *a, **k):
        pass


class _Entry:
    """Stand-in del campo CSV della GUI (`_e_csv`): `.get()` ritorna il valore."""

    def __init__(self, value=""):
        self._v = value

    def get(self):
        return self._v


@pytest.fixture
def app_mod():
    return _app_mod


@pytest.fixture
def make_app():
    """Factory di una `App` HEADLESS con collaboratori REALI e sink GUI catturati.

    Liste di cattura sull'istanza: `logs`, `expiry_calls` (path, delay passati a
    `_schedule_expiry`), `guard_saves`, `processed`/`confirmations` (per i test del
    listener, dove `_process`/`_process_confirmation` sono shadowati)."""

    def _factory(*, csv_path=None, running=True, config=None, queue=None,
                 tracker=None, daily=None, gui_csv="", capture_schedule=True):
        a = object.__new__(_app_mod.App)
        # stato runtime reale
        a._running = running
        a._config = {} if config is None else config
        a._active_csv_path = csv_path
        a._queue = queue
        a._queue_lock = threading.Lock()
        a._tracker = tracker
        a._daily = daily
        a._csv_lock = _app_mod.csv_lock_escalation.CsvLockEscalation()
        a._expire_timer = None
        a._stop_event = threading.Event()
        a._loop = None
        a._tg_app = None
        a._queue_timeout = 120
        a._listener_epoch = 1
        a._reconnect_attempt = 0
        # cattura
        a.logs = []
        a.expiry_calls = []
        a.guard_saves = []
        a.processed = []
        a.confirmations = []
        # sink GUI: no-op / cattura (la presentazione non è oggetto del test della glue)
        a._log = a.logs.append
        a._dbg = lambda *x, **k: None
        # `after(ms, func, *args)`: esegue SUBITO il callback (come se il main loop Tk
        # lo avesse processato), così i side-effect GUI shadowati (log/bump/...) avvengono
        # e i log dei rami d'errore — emessi dalla glue via self.after — sono verificabili.
        a.after = lambda delay=None, func=None, *x, **k: (func(*x) if callable(func) else None)
        a._bump = lambda *x, **k: None
        a._set_last = lambda *x, **k: None
        a._note_csv = lambda *x, **k: None
        a._update_active_indicator = lambda *x, **k: None
        a._update_real_mode_banner = lambda *x, **k: None
        a._cancel_pending_autostart = lambda *x, **k: None
        a._refresh_dashboard = lambda *x, **k: None
        a._save_guard_state = lambda: a.guard_saves.append(True)
        if capture_schedule:
            # niente Timer reale: cattura la richiesta di (ri)programmazione, così i test
            # restano deterministici e si verifica COMUNQUE che la glue abbia chiesto un retry.
            a._schedule_expiry = lambda path, delay=None: a.expiry_calls.append((path, delay))
        a._status_lbl = _Widget()
        a._btn_start = _Widget()
        a._btn_stop = _Widget()
        a._e_csv = _Entry(gui_csv)
        return a

    return _factory
