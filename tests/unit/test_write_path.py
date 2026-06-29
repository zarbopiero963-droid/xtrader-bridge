"""Test hard della sezione critica del percorso di scrittura (`write_path.commit_signal`).

Esercita il CUORE anti-doppia-scommessa con collaboratori REALI (SignalQueue,
SignalTracker, DailyLimiter) e una `write_rows` iniettabile: scrittura riuscita,
fallimento con ROLLBACK completo (coda + dedup + daily), blocco dal tetto righe attive
con rollback dei guardrail (segnale ritentabile), esito non-WRITE (duplicato) che non
tocca la coda, e `tracker=None`.

NB: il lock è responsabilità del chiamante (`App._process`); qui si testa la logica
sotto-lock in isolamento, headless.
"""

from xtrader_bridge import (
    live_guard,
    safety_guard,
    signal_dedupe,
    signal_queue,
    write_path,
)

CFG_REAL = {"dry_run": False}        # scrittura operativa (non simulazione)


def _row(name):
    return {"EventName": name, "SelectionName": name, "Price": "1,90"}


def _ok_writer(sink):
    """write_rows che registra le righe scritte (scrittura riuscita)."""
    def _w(rows, path):
        sink.append([dict(r) for r in rows])
    return _w


def _boom_writer(exc=OSError("CSV locked")):
    """write_rows che fallisce sempre (file bloccato/permessi)."""
    def _w(rows, path):
        raise exc
    return _w


def _fresh(mode=signal_queue.OVERWRITE_LAST, max_active=0, max_per_day=10):
    tracker = signal_dedupe.SignalTracker()
    daily = safety_guard.DailyLimiter(max_per_day=max_per_day)
    queue = signal_queue.SignalQueue(mode=mode, max_active=max_active)
    return tracker, daily, queue


def test_write_riuscita_accoda_e_scrive():
    tracker, daily, queue = _fresh()
    written = []
    row = _row("A")
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "msgA", row, "out.csv", 100.0, _ok_writer(written))
    assert res.decision == live_guard.WRITE
    assert res.write_error is None
    assert res.blocked_by_cap is False
    assert res.rows == [row]
    assert written == [[row]]            # CSV scritto una volta con la riga
    assert queue.active_rows() == [row]  # segnale attivo in coda


def test_write_fallita_fa_rollback_completo_e_segnale_ritentabile():
    tracker, daily, queue = _fresh()
    row = _row("A")
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "msgA", row, "out.csv", 100.0, _boom_writer())
    # Esito: errore riportato, NON sollevato
    assert isinstance(res.write_error, OSError)
    assert res.decision == live_guard.WRITE
    # Coda ripristinata: la riga NON resta attiva (niente riga stantia se la write fallisce)
    assert queue.active_rows() == []
    # Dedup ripristinato: lo STESSO messaggio non è un duplicato → ritentabile come WRITE
    written = []
    res2 = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "msgA", row, "out.csv", 101.0, _ok_writer(written))
    assert res2.decision == live_guard.WRITE   # non DUPLICATE: il dedup era stato annullato
    assert res2.write_error is None
    assert written == [[row]]


def test_blocco_da_tetto_scrive_correnti_e_fa_rollback_guardrail():
    # tetto 1: A occupa la riga, B (diverso) è oltre il tetto → bloccato.
    tracker, daily, queue = _fresh(mode=signal_queue.APPEND_ACTIVE, max_active=1)
    rowA, rowB = _row("A"), _row("B")
    write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "msgA", rowA, "out.csv", 100.0, _ok_writer([]))
    written = []
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "msgB", rowB, "out.csv", 101.0, _ok_writer(written))
    assert res.decision == live_guard.WRITE
    assert res.blocked_by_cap is True
    # Scrive le righe ATTIVE correnti (solo A): B non è accodato
    assert res.rows == [rowA]
    assert written == [[rowA]]
    assert [r["EventName"] for r in queue.active_rows()] == ["A"]
    # Guardrail rollback → B è RITENTABILE: registrarlo ora NON è un duplicato
    reg = tracker.register("msgB")
    assert reg.status != signal_dedupe.DUPLICATE


def test_duplicato_non_scrive_e_non_tocca_la_coda():
    tracker, daily, queue = _fresh()
    row = _row("A")
    write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "dup", row, "out.csv", 100.0, _ok_writer([]))
    before = queue.active_rows()
    written = []
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "dup", row, "out.csv", 101.0, _ok_writer(written))
    assert res.decision == live_guard.DUPLICATE
    assert res.blocked_by_cap is False
    assert res.rows == []
    assert written == []                 # nessuna scrittura tentata
    assert queue.active_rows() == before  # coda invariata


def test_dry_run_non_scrive():
    tracker, daily, queue = _fresh()
    written = []
    res = write_path.commit_signal(
        tracker, daily, queue, {"dry_run": True}, "msgA", _row("A"), "out.csv", 100.0,
        _ok_writer(written))
    assert res.decision == live_guard.DRY_RUN
    assert res.rows == []
    assert written == []
    assert queue.active_rows() == []     # in simulazione la coda non viene toccata


# ── #184 low-tracker-nonwrite: i guardrail riflettono SOLO i WRITE reali ──────

CFG_DRY = {"dry_run": True}


def test_dry_run_non_consuma_il_tetto_giornaliero_reale():
    """#184 low-tracker-nonwrite: in simulazione `evaluate` incrementava il `DailyLimiter` reale
    (allow() conta), quindi N segnali in DRY_RUN esaurivano il tetto e poi BLOCCAVANO i segnali
    reali. Ora DRY_RUN fa rollback del tetto: la simulazione non consuma quota reale.

    Fail-first: senza rollback, `daily.remaining()` scendeva ad ogni segnale dry-run."""
    tracker, daily, queue = _fresh(max_per_day=2)
    for i in range(5):                                  # 5 segnali DIVERSI in simulazione
        res = write_path.commit_signal(
            tracker, daily, queue, CFG_DRY, f"sim{i}", _row(f"S{i}"), "out.csv", 100.0 + i,
            _ok_writer([]))
        assert res.decision == live_guard.DRY_RUN
    assert daily.remaining() == 2                        # tetto intatto: nessuna quota consumata


def test_dry_run_non_consuma_il_dedupe_reale():
    """#184 low-tracker-nonwrite: un segnale visto in DRY_RUN non deve poi sopprimere il SUO
    piazzamento reale (passando a modalità reale). Ora il dedupe non trattiene gli hash dry-run.

    Fail-first: senza rollback, lo stesso messaggio in reale dava DUPLICATE → bet reale persa."""
    tracker, daily, queue = _fresh()
    write_path.commit_signal(
        tracker, daily, queue, CFG_DRY, "segnale", _row("A"), "out.csv", 100.0, _ok_writer([]))
    written = []
    res = write_path.commit_signal(                      # ora in REALE, stesso messaggio
        tracker, daily, queue, CFG_REAL, "segnale", _row("A"), "out.csv", 101.0,
        _ok_writer(written))
    assert res.decision == live_guard.WRITE              # NON DUPLICATE: il dry-run non l'ha trattenuto
    assert written == [[_row("A")]]


def test_daily_limited_resta_ritentabile_dopo_il_reset():
    """#184 low-tracker-nonwrite: un segnale bloccato dal tetto giornaliero non deve restare
    soppresso come DUPLICATE dopo il reset del giorno. Ora DAILY_LIMITED fa rollback del dedupe.

    Fail-first: senza rollback, dopo il reset lo stesso messaggio dava DUPLICATE → bet persa.

    NB: `evaluate` usa il wallclock interno del DailyLimiter (non il `now` della coda), quindi il
    reset del giorno si simula azzerando il contatore via `restore_state` (stesso giorno valido)."""
    tracker, daily, queue = _fresh(max_per_day=1)
    # A consuma l'unica slot e viene scritto; B (diverso) è oltre il tetto → DAILY_LIMITED.
    write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "A", _row("A"), "out.csv", 100.0, _ok_writer([]))
    resB = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "B", _row("B"), "out.csv", 101.0, _ok_writer([]))
    assert resB.decision == live_guard.DAILY_LIMITED
    # Reset del tetto (nuovo giorno): azzera il contatore, lasciando intatto lo stato dedupe.
    snap = daily.state()
    daily.restore_state({**snap, "count": 0})
    # B deve poter essere scritto, NON soppresso come duplicato (il suo hash era stato annullato).
    written = []
    resB2 = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "B", _row("B"), "out.csv", 102.0, _ok_writer(written))
    assert resB2.decision == live_guard.WRITE
    assert written == [[_row("B")]]


def test_daily_limited_giorno_corrotto_resta_normalizzato_non_si_blocca():
    """#184 low-tracker-nonwrite (Codex P2): con un `daily_state` corrotto (giorno malformato) e
    count al tetto, `allow()` rifiuta MA normalizza `_day` a oggi. Il rollback NON deve scartare
    quella normalizzazione: altrimenti il giorno corrotto verrebbe ri-salvato e il bridge resterebbe
    bloccato per sempre (mai un reset domani).

    Fail-first: col rollback pieno del daily, `_day` tornava al valore corrotto (UNKNOWN)."""
    tracker = signal_dedupe.SignalTracker()
    daily = safety_guard.DailyLimiter(max_per_day=1)
    # Stato corrotto tollerato da restore_state: giorno non valido → UNKNOWN, count al tetto.
    assert daily.restore_state({"day": "20XX-99-99", "count": 1}) is True
    assert not safety_guard._is_valid_day(daily.state()["day"])     # baseline: giorno NON valido
    queue = signal_queue.SignalQueue(mode=signal_queue.OVERWRITE_LAST, max_active=0)
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "B", _row("B"), "out.csv", 100.0, _ok_writer([]))
    assert res.decision == live_guard.DAILY_LIMITED
    # Il giorno è stato NORMALIZZATO a una data valida (oggi), non riportato al valore corrotto:
    # così al prossimo giorno reale il tetto si resetterà invece di restare bloccato.
    assert safety_guard._is_valid_day(daily.state()["day"])


def test_dry_run_giorno_corrotto_resta_normalizzato_e_slot_restituita():
    """#184 low-tracker-nonwrite (Codex P2): anche in DRY_RUN il rollback non deve riportare un
    giorno corrotto. `release()` disfa la sola slot consumata, mantenendo la normalizzazione.

    Fail-first: col rollback pieno del daily, `_day` tornava al valore corrotto (UNKNOWN)."""
    tracker = signal_dedupe.SignalTracker()
    daily = safety_guard.DailyLimiter(max_per_day=5)
    assert daily.restore_state({"day": "bad-day", "count": 0}) is True
    assert not safety_guard._is_valid_day(daily.state()["day"])
    queue = signal_queue.SignalQueue(mode=signal_queue.OVERWRITE_LAST, max_active=0)
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_DRY, "S", _row("S"), "out.csv", 100.0, _ok_writer([]))
    assert res.decision == live_guard.DRY_RUN
    assert safety_guard._is_valid_day(daily.state()["day"])         # giorno normalizzato, non corrotto
    assert daily.remaining() == 5                                    # slot restituita (release)


def test_write_reale_resta_deduplicato_nessuna_doppia_scommessa():
    """#184 low-tracker-nonwrite (guardia anti-regressione): un WRITE reale CONSUMA ancora il
    dedupe, quindi un re-send identico nella finestra resta DUPLICATE → nessuna doppia scommessa."""
    tracker, daily, queue = _fresh()
    write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "X", _row("X"), "out.csv", 100.0, _ok_writer([]))
    written = []
    res = write_path.commit_signal(
        tracker, daily, queue, CFG_REAL, "X", _row("X"), "out.csv", 101.0, _ok_writer(written))
    assert res.decision == live_guard.DUPLICATE          # ancora soppresso
    assert written == []


def test_tracker_none_scrive_come_write():
    # Nessun guardrail (tracker None) → decisione di default WRITE.
    _, _, queue = _fresh()
    written = []
    row = _row("A")
    res = write_path.commit_signal(
        None, None, queue, CFG_REAL, "msgA", row, "out.csv", 100.0, _ok_writer(written))
    assert res.decision == live_guard.WRITE
    assert res.write_error is None
    assert written == [[row]]
