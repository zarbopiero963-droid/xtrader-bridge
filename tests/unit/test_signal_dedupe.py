"""Test della deduplica e del limite/minuto del segnale (PR-15/#5)."""

from xtrader_bridge import signal_dedupe as sd


MSG = "🔔 P.Bet.\nInter v Milan\nMercato: GG\nQuota 1,85"


# ── message_hash ─────────────────────────────────────────────────────────────

def test_hash_stabile_e_normalizzato():
    # Stesso messaggio (anche con spaziatura diversa) → stesso hash.
    assert sd.message_hash("Inter v Milan") == sd.message_hash("  Inter   v  Milan  ")
    # Messaggi diversi → hash diversi.
    assert sd.message_hash("Inter v Milan") != sd.message_hash("Milan v Inter")


# ── deduplica ────────────────────────────────────────────────────────────────

def test_stesso_messaggio_due_volte_e_duplicato():
    t = sd.SignalTracker()
    assert t.register(MSG, now=1000).status == sd.NEW
    assert t.register(MSG, now=1001).status == sd.DUPLICATE


def test_due_segnali_diversi_stessa_partita_ammessi():
    # Stessa partita ma mercato/esito diversi → testo diverso → entrambi NEW.
    t = sd.SignalTracker()
    a = "Inter v Milan\nMercato: GG\nQuota 1,85"
    b = "Inter v Milan\nMercato: Over 2,5\nQuota 1,90"
    assert t.register(a, now=1000).status == sd.NEW
    assert t.register(b, now=1001).status == sd.NEW


def test_duplicato_scade_dopo_la_finestra():
    t = sd.SignalTracker(dedupe_window=300)
    assert t.register(MSG, now=1000).status == sd.NEW
    # oltre la finestra (300s) lo stesso messaggio è di nuovo NEW
    assert t.register(MSG, now=1000 + 301).status == sd.NEW


# ── limite al minuto ─────────────────────────────────────────────────────────

def test_limite_al_minuto():
    t = sd.SignalTracker(max_per_minute=20, dedupe_window=300)
    # 20 messaggi distinti nello stesso minuto → tutti NEW
    for i in range(20):
        assert t.register(f"segnale numero {i}", now=1000 + i).status == sd.NEW
    # il 21esimo nello stesso minuto → RATE_LIMITED
    assert t.register("segnale numero 20", now=1019).status == sd.RATE_LIMITED


def test_limite_si_libera_dopo_un_minuto():
    t = sd.SignalTracker(max_per_minute=2, dedupe_window=600)
    assert t.register("a", now=1000).status == sd.NEW
    assert t.register("b", now=1001).status == sd.NEW
    assert t.register("c", now=1002).status == sd.RATE_LIMITED   # 2/min raggiunto
    # passato un minuto dai primi, c'è di nuovo spazio
    assert t.register("d", now=1062).status == sd.NEW


def test_rate_limited_non_memorizzato_non_diventa_duplicato():
    t = sd.SignalTracker(max_per_minute=1, dedupe_window=600)
    assert t.register("a", now=1000).status == sd.NEW
    assert t.register("b", now=1001).status == sd.RATE_LIMITED
    # "b" non è stato memorizzato: dopo che si libera il minuto, è NEW (non duplicato)
    assert t.register("b", now=1062).status == sd.NEW


# ── persistenza: riconoscimento duplicati dopo un riavvio ────────────────────

def test_restart_riconosce_duplicati_recenti(tmp_path):
    path = str(tmp_path / "history.json")
    t1 = sd.SignalTracker()
    assert t1.register(MSG, now=1000).status == sd.NEW
    assert sd.save_state(t1, path) is True
    # "riavvio": nuovo tracker che ricarica lo stato
    t2 = sd.SignalTracker()
    assert sd.load_state(t2, path) is True
    assert t2.register(MSG, now=1002).status == sd.DUPLICATE


def test_load_state_file_assente_lascia_invariato(tmp_path):
    t = sd.SignalTracker()
    assert sd.load_state(t, str(tmp_path / "manca.json")) is False
    assert t.register(MSG, now=1000).status == sd.NEW


def test_restore_state_tollera_voci_malformate():
    t = sd.SignalTracker()
    t.restore_state([["hashvalido", 1000], "rotta", [1, 2, 3], ["altro", "nan?"]])
    # solo la voce valida viene ripristinata
    assert t.state() == [["hashvalido", 1000.0]]
