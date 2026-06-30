"""Test hard del login Betfair NON bloccante per la GUI (issue #184 H1 + review Codex).

Prima del fix la callback «Accedi» eseguiva `login()` (POST HTTPS, fino a ~20s) DIRETTAMENTE
nel main thread Tk → finestra congelata. Ora il login gira su un WORKER THREAD e l'esito è
marshalato con `after(0, ...)`, con: flag anti-rientro, guardia di chiusura (`_closing`) e un
**epoch** che scarta i completamenti stantii (logout/«Cancella credenziali» durante il login).
Si esercitano i METODI REALI di `App` (headless harness).
"""

import threading
import types


class _FakeAuth:
    """Client di login finto: registra le chiamate; può sollevare un'eccezione."""

    def __init__(self, exc=None):
        self.exc = exc
        self.calls = []

    def login(self, creds):
        self.calls.append(creds)
        if self.exc is not None:
            raise self.exc


class _FakeEngine:
    def __init__(self):
        self.app_key = None

    def set_app_key(self, key):
        self.app_key = key


class _FakeEngineReserve(_FakeEngine):
    """Engine finto che espone reserve()/release() (come `SyncEngine`), per i test della
    serializzazione login manuale ↔ auto-sync (#172 audit)."""

    def __init__(self, reserve_ok=True):
        super().__init__()
        self._reserve_ok = reserve_ok
        self.events = []

    def reserve(self, blocking=False):
        self.events.append("reserve")
        return self._reserve_ok

    def release(self):
        self.events.append("release")


# ── _betfair_login_work: logica bloccante isolata (no Tk) ─────────────────────

def test_betfair_login_work_successo_porta_appkey_nell_engine(make_app):
    a = make_app(running=True)
    a._betfair_auth_obj = _FakeAuth()
    a._betfair_engine_obj = _FakeEngine()
    creds = types.SimpleNamespace(app_key="APPKEY")
    msg = a._betfair_login_work(creds)
    assert "riuscito" in msg.lower()
    assert a._betfair_auth_obj.calls == [creds]              # login realmente chiamato
    assert a._betfair_engine_obj.app_key == "APPKEY"         # app key del login → engine


def test_betfair_login_work_fallito_e_safe(make_app):
    from xtrader_bridge.betfair.auth_client import LoginError
    a = make_app(running=True)
    a._betfair_auth_obj = _FakeAuth(exc=LoginError("status 403"))
    a._betfair_engine_obj = _FakeEngine()
    creds = types.SimpleNamespace(app_key="SEGRETISSIMO")
    msg = a._betfair_login_work(creds)
    assert "fallito" in msg.lower()
    assert "SEGRETISSIMO" not in msg                          # nessun segreto nel messaggio


def test_betfair_login_work_prenota_il_motore_e_rilascia(make_app):
    # #172 audit (Codex): il login manuale PRENOTA il lock del motore prima del login e lo
    # rilascia dopo, serializzandosi con l'auto-sync sulla sessione condivisa (così il
    # logout finale dell'auto-sync non slogga una sessione appena creata a mano).
    a = make_app(running=True)
    a._betfair_auth_obj = _FakeAuth()
    eng = _FakeEngineReserve(reserve_ok=True)
    a._betfair_engine_obj = eng
    creds = types.SimpleNamespace(app_key="K")
    msg = a._betfair_login_work(creds)
    assert "riuscito" in msg.lower()
    assert a._betfair_auth_obj.calls == [creds]          # login eseguito
    assert eng.app_key == "K"                            # app key portata nell'engine
    assert eng.events[0] == "reserve"                    # prenotato PRIMA del login
    assert eng.events[-1] == "release"                   # e rilasciato dopo


def test_betfair_login_work_motore_occupato_rimanda_il_login(make_app):
    # Se il motore è già prenotato (sync manuale o auto-sync in corso), il login manuale è
    # RIMANDATO: non chiama login (non tocca la sessione condivisa) e non rilascia un lock
    # che non ha preso.
    a = make_app(running=True)
    a._betfair_auth_obj = _FakeAuth()
    eng = _FakeEngineReserve(reserve_ok=False)
    a._betfair_engine_obj = eng
    msg = a._betfair_login_work(types.SimpleNamespace(app_key="K"))
    assert "rimandato" in msg.lower()
    assert a._betfair_auth_obj.calls == []               # NESSUN login sulla sessione condivisa
    assert eng.events == ["reserve"]                     # niente release (lock non preso da noi)


def test_betfair_autosync_seed_usa_config_live_non_disco(make_app):
    # #172 audit (Codex): il pannello Betfair va seminato dalla config LIVE in memoria, non
    # da una rilettura del disco (stantia dopo un save fallito), altrimenti un edit
    # successivo riscriverebbe valori vecchi sopra la config viva.
    a = make_app(running=True, config={"betfair_auto_sync": True,
                                       "betfair_auto_sync_hour": 9,
                                       "betfair_sync_sports": ["Tennis"]})
    # Se per errore leggesse il disco, otterrebbe valori DIVERSI: il test lo smaschera.
    a._load_config = lambda: {"betfair_auto_sync": False, "betfair_auto_sync_hour": 23,
                              "betfair_sync_sports": ["Calcio"]}
    seed = a._betfair_autosync_seed()
    assert seed == {"enabled": True, "hour": 9, "sports": ["Tennis"]}


def test_betfair_login_work_engine_assente_non_crasha(make_app):
    a = make_app(running=True)
    a._betfair_auth_obj = _FakeAuth()

    class _BoomEngine:
        def set_app_key(self, key):
            raise RuntimeError("DB non apribile")

    a._betfair_engine_obj = _BoomEngine()
    msg = a._betfair_login_work(types.SimpleNamespace(app_key="K"))
    assert "riuscito" in msg.lower()                          # login ok comunque


# ── _betfair_login_async: offload su worker thread + anti-rientro ─────────────

def test_betfair_login_async_gira_su_worker_thread(make_app):
    a = make_app(running=True)
    a._closing = False
    a.winfo_exists = lambda: True
    main_tid = threading.get_ident()
    seen = {}

    def _fake_work(creds):
        seen["tid"] = threading.get_ident()
        return "🔵 ok"

    a._betfair_login_work = _fake_work
    a._betfair_login_async(types.SimpleNamespace(app_key="K"))
    a._betfair_login_thread.join(timeout=5)                   # deterministico

    assert seen["tid"] != main_tid                            # H1: login NON sul main thread
    assert a._betfair_login_busy is False                     # flag liberato a fine login
    assert a.logs[-1] == "🔵 ok"                              # esito marshalato e loggato


def test_betfair_login_async_non_rientrante(make_app):
    a = make_app(running=True)
    a._betfair_login_busy = True
    called = []
    a._betfair_login_work = lambda creds: called.append(1) or "x"
    a._betfair_login_async(types.SimpleNamespace(app_key="K"))
    assert called == []                                       # nessun secondo login parte


def test_betfair_login_async_non_rientra_in_tk_a_chiusura(make_app):
    # Teardown (Codex): se l'app si sta chiudendo, il worker NON chiama `after` su una
    # root distrutta.
    a = make_app(running=True)
    a._closing = True
    after_calls = []
    a.after = lambda *x, **k: after_calls.append(x)
    a._betfair_login_work = lambda creds: "x"
    a._betfair_login_async(types.SimpleNamespace(app_key="K"))
    a._betfair_login_thread.join(timeout=5)
    assert after_calls == []                                  # niente Tk a chiusura
    assert a._betfair_login_busy is False


def test_betfair_login_async_schedule_fallito_non_crasha(make_app):
    # Race teardown (Codex): se la root viene distrutta TRA il check `_closing` e `after`,
    # lo schedule solleva (Tcl/RuntimeError): va catturato, niente eccezione sul daemon thread.
    a = make_app(running=True)
    a._closing = False

    def _boom_after(*x, **k):
        raise RuntimeError("Tcl_Eval: application has been destroyed")

    a.after = _boom_after
    a._betfair_login_work = lambda creds: "x"
    a._betfair_login_async(types.SimpleNamespace(app_key="K"))
    a._betfair_login_thread.join(timeout=5)                   # il thread NON deve propagare
    assert a._betfair_login_busy is False


def test_betfair_login_async_completamento_stantio_scartato(make_app):
    # Stale completion (Codex): logout/«Cancella credenziali» durante un login lento →
    # il login in volo è stantio: scarta il token appena settato e NON riporta a «connesso».
    a = make_app(running=True)
    a._closing = False
    cleared = []
    a._betfair_session_obj = lambda: types.SimpleNamespace(clear=lambda: cleared.append(True))

    def _fake_work(creds):
        a._betfair_invalidate_login()                        # logout/delete durante il login
        return "🔵 connesso"

    a._betfair_login_work = _fake_work
    a._betfair_login_async(types.SimpleNamespace(app_key="K"))
    a._betfair_login_thread.join(timeout=5)

    assert cleared == [True]                                  # token stantio scartato
    assert a.logs == []                                       # nessun «connesso» dopo il logout
    assert a._betfair_login_busy is False


# ── _betfair_login_done: epoch + guardie root ────────────────────────────────

def test_betfair_login_done_logga_se_corrente(make_app):
    a = make_app(running=True)
    a._closing = False
    a.winfo_exists = lambda: True
    a._betfair_login_busy = True
    a._betfair_login_epoch = 5
    a._betfair_login_done("✅ esito", 5)                      # gen corrente
    assert a._betfair_login_busy is False
    assert a.logs[-1] == "✅ esito"


def test_betfair_login_done_ignora_completamento_stantio(make_app):
    a = make_app(running=True)
    a._closing = False
    a.winfo_exists = lambda: True
    a._betfair_login_epoch = 6                                # epoch avanzato (logout/delete)
    a._betfair_login_done("✅ vecchio", 5)                    # gen vecchio
    assert a.logs == []                                       # stantio: niente log


def test_betfair_login_done_ignora_root_in_chiusura(make_app):
    a = make_app(running=True)
    a._closing = True
    a._betfair_login_epoch = 1
    a._betfair_login_done("x", 1)
    assert a.logs == []                                       # root in chiusura: niente Tk


# ── invalidate / discard ─────────────────────────────────────────────────────

def test_betfair_invalidate_login_bumpa_epoch(make_app):
    a = make_app(running=True)
    e0 = a._betfair_login_epoch
    a._betfair_invalidate_login()
    assert a._betfair_login_epoch == e0 + 1


def test_betfair_discard_stale_login_pulisce_sessione(make_app):
    a = make_app(running=True)
    cleared = []
    a._betfair_session_obj = lambda: types.SimpleNamespace(clear=lambda: cleared.append(True))
    a._betfair_discard_stale_login()
    assert cleared == [True]


# ── panel: logout/delete invalidano un login in volo ─────────────────────────

def test_panel_logout_e_delete_invalidano_login_PRIMA_dell_azione():
    import pytest
    pytest.importorskip("customtkinter")   # il widget richiede la GUI (assente in locale)
    from xtrader_bridge.betfair.sync_tab_gui import BetfairSyncPanel

    p = object.__new__(BetfairSyncPanel)
    order = []
    p._on_invalidate = lambda: order.append("invalidate")
    p.controller = types.SimpleNamespace(
        logout=lambda: order.append("logout"),
        delete_saved_credentials=lambda: order.append("delete") or True)
    p._action_status = types.SimpleNamespace(configure=lambda **k: None)
    p._refresh_buttons = lambda: None
    p._reload = lambda: None

    p._logout()
    assert order == ["invalidate", "logout"]     # invalida PRIMA del logout (Codex)
    order.clear()
    p._delete()
    assert order == ["invalidate", "delete"]      # invalida PRIMA della cancellazione
