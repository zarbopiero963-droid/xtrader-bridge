"""Sezione critica del percorso di scrittura del segnale (#136 item 1, slice 6).

Estratta da `App._process`: la sequenza **valuta-guardrail → coda → scrittura CSV →
rollback**, cioè il cuore anti-doppia-scommessa. Tenerla qui la rende esercitabile in
CI con coda/tracker/daily **reali** e una `write_rows` iniettabile che può fallire.

INVARIANTI (non negoziabili):
- **Lock del chiamante.** `commit_signal` NON prende il lock: `App._process` lo invoca
  mentre tiene `_queue_lock`. `SignalTracker`/`DailyLimiter`/`SignalQueue` non hanno lock
  interno, e la sequenza «valuta + scrivi» deve restare atomica (audit A2), altrimenti
  due callback interlacciati potrebbero passare entrambi il dedup → doppia scommessa.
- **Solo WRITE scrive.** Ogni altro esito `live_guard` (DUPLICATE/RATE_LIMITED/
  DAILY_LIMITED/DRY_RUN) sopprime la scrittura e non tocca la coda. Inoltre lo stato dei
  guardrail riflette SOLO i WRITE reali: il consumo fatto da `evaluate` su un esito che NON
  scrive viene disfatto. DAILY_LIMITED → si annulla solo l'hash del tracker (il tetto non aveva
  consumato slot, solo normalizzato il giorno: si preserva, altrimenti un giorno corrotto
  bloccherebbe per sempre). DRY_RUN → si annulla l'hash e si **restituisce** la slot giornaliera
  con `DailyLimiter.release()` (mantenendo il giorno normalizzato). Così la simulazione non
  consuma tetto/dedupe reali e un segnale soppresso resta ritentabile, senza rischio di doppia
  scommessa (#184 low-tracker-nonwrite).
- **Rollback fail-safe.** Se la scrittura CSV fallisce, coda E guardrail tornano allo
  stato precedente (allineati al CSV ancora su disco): il segnale resta RITENTABILE e in
  OVERWRITE_LAST il precedente non va perso. Stesso rollback dei guardrail quando il
  segnale è oltre il tetto di righe attive (#136 p5): non accodato → ritentabile.
- **Nessun side-effect oltre `write_rows`.** Niente GUI, niente persistenza su disco dei
  guardrail (resta a carico di `App` dopo il commit), niente eccezioni propagate per un
  fallimento di scrittura (riportato in `CommitResult.write_error`).

`evaluate` (dedup/limiti/dry-run) è chiamato SENZA `now`: il dedup usa il proprio
wallclock persistito; `now` (monotòno) serve solo alla coda (expire/add), come in origine.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import live_guard, safety_guard, signal_dedupe, signal_queue


@dataclass(frozen=True)
class CommitResult:
    """Esito della sezione critica.

    - `decision`: esito `live_guard` (WRITE o un esito che sopprime la scrittura);
    - `blocked_by_cap`: True se — pur essendo WRITE — il nuovo segnale è oltre il tetto
      di righe attive (#136 p5): NON accodato, guardrail già ripristinati;
    - `rows`: righe attive scritte (post-expire) nel ramo WRITE; `[]` altrimenti;
    - `write_error`: l'eccezione se la scrittura CSV è fallita (con rollback completo),
      altrimenti `None`.
    """

    decision: str
    blocked_by_cap: bool
    rows: list
    write_error: BaseException | None


def commit_signal(tracker, daily, queue, cfg, text, row, path, now, write_rows):
    """Esegue, SOTTO IL LOCK DEL CHIAMANTE, la sequenza valuta-guardrail → coda →
    scrittura con rollback fail-safe (vedi il docstring del modulo per le invarianti).

    Ritorna una `CommitResult`. Non solleva mai per un fallimento di scrittura: ripristina
    coda E guardrail e riporta l'eccezione in `write_error`."""
    decision = live_guard.WRITE
    blocked_by_cap = False
    rows = []
    write_error = None
    tracker_snap = daily_snap = None

    # `tracker is None` (test/chiamanti senza guardrail) → resta WRITE di default.
    if tracker is not None:
        tracker_snap = tracker.state()
        daily_snap = daily.state() if daily is not None else None
        decision = live_guard.evaluate(cfg, tracker, daily, text)

    if decision == live_guard.WRITE:
        # Coda dei segnali attivi: expire dei già scaduti, add del nuovo, riscrittura
        # atomica di TUTTE le righe attive. Snapshot per il rollback su write fallita.
        queue_snap = queue.state()
        queue.expire(now=now)
        sid = queue.add(row, now=now)
        # `add` ritorna None se il nuovo segnale è oltre il tetto (#136 p5): le righe
        # attive restano quelle correnti (post-expire), il CSV è comunque riscritto.
        blocked_by_cap = sid is None
        rows = queue.active_rows()
        try:
            write_rows(rows, path)
        except Exception as ex:   # noqa: BLE001 — riportato al chiamante, no crash
            # Scrittura fallita: RIPRISTINA coda E guardrail (allineati al CSV su disco).
            queue.restore_state(queue_snap)
            if tracker is not None:
                tracker.restore_state(tracker_snap)
                if daily is not None and daily_snap is not None:
                    daily.restore_state(daily_snap)
            write_error = ex
        else:
            if blocked_by_cap and tracker is not None:
                # Bloccato dal tetto: segnale NON accodato → rollback guardrail (ritentabile).
                tracker.restore_state(tracker_snap)
                if daily is not None and daily_snap is not None:
                    daily.restore_state(daily_snap)
    elif tracker is not None and decision == live_guard.DAILY_LIMITED:
        # `evaluate` aveva registrato l'hash nel tracker (segnale NEW) ma `daily.allow()` ha
        # RIFIUTATO **senza consumare** una slot — ha solo (eventualmente) normalizzato il giorno
        # corrente. Si annulla SOLO l'hash del tracker (segnale ritentabile dopo il reset), NON si
        # tocca il daily: ripristinare il suo snapshot riporterebbe un giorno corrotto (state file
        # malformato) e lascerebbe il bridge bloccato per sempre (#184 low-tracker-nonwrite, Codex).
        tracker.restore_state(tracker_snap)
    elif tracker is not None and decision == live_guard.DRY_RUN:
        # Simulazione: `evaluate` ha registrato l'hash E consumato una slot giornaliera REALE per un
        # segnale MAI scritto. Si annulla l'hash e si RESTITUISCE la slot con `release()` (decremento
        # che MANTIENE il giorno normalizzato): così la simulazione non intacca tetto/dedupe reali
        # senza scartare la normalizzazione del giorno. DUPLICATE/RATE_LIMITED non aggiungono nulla.
        tracker.restore_state(tracker_snap)
        if daily is not None:
            daily.release()

    return CommitResult(decision=decision, blocked_by_cap=blocked_by_cap,
                        rows=rows, write_error=write_error)


def _summary_decision(decisions: list, accepted: int) -> str:
    """Esito riassuntivo del commit multi-riga: WRITE se almeno una riga è stata accodata,
    altrimenti il primo esito di soppressione (DUPLICATE/RATE_LIMITED/DAILY_LIMITED) per la
    diagnostica."""
    if accepted > 0:
        return live_guard.WRITE
    for d in decisions:
        if d != live_guard.WRITE:
            return d
    return live_guard.WRITE


def commit_signals(tracker, daily, queue, cfg, text, rows, path, now, write_rows):
    """Commit MULTI-RIGA (#192): un singolo messaggio produce più righe (MultiMarket/
    MultiSelection). Valuta OGNI riga con **deduplica PER-RIGA** (`signal_dedupe.row_dedup_key`),
    accoda le righe `WRITE` e riscrive ATOMICAMENTE tutte le righe attive, con rollback fail-safe.

    Stesse invarianti di `commit_signal` (vedi docstring del modulo): chiamato SOTTO il lock del
    chiamante; solo le righe `WRITE` finiscono in coda; in `DRY_RUN` il CSV operativo NON viene
    scritto e i guardrail consumati sono ripristinati; se la scrittura fallisce, coda E guardrail
    tornano allo stato precedente (segnali ritentabili). Per il single-row usare `commit_signal`
    (percorso legacy, comportamento bit-identico e invariato).

    Accodamento per modo coda (Codex/CodeRabbit #239/#192):
    - `OVERWRITE_LAST`: l'«ultima istruzione» è il BLOCCO INTERO del messaggio. Il blocco riscritto
      contiene TUTTE le righe dell'istruzione ancora valide: le righe NUOVE (`WRITE`) **più** le
      righe `DUPLICATE` che sono **ancora attive** in coda. Così un messaggio che prima produceva
      A e poi (cambio config, stesso testo) produce A+B NON perde A: senza questa preservazione,
      `replace_block` ricostruirebbe il blocco dalle sole righe nuove e scarterebbe A già attiva
      (kyh #192, Codex #281). Il CSV è riscritto SOLO se c'è almeno una riga NUOVA (come il
      single-row su WRITE): un reinvio identico (tutte duplicate) non tocca il CSV, così XTrader
      non riconsuma righe identiche riscritte.
    - `APPEND_ACTIVE`/`QUEUE_UNTIL_CONFIRMED`: `queue.add(..., force=True)` per ogni riga NUOVA →
      **auto-raise del tetto** (decisione proprietario #192): il blocco coerente di UN messaggio
      multi NON viene MAI spezzato dal tetto `max_active`. Elimina alla radice il partial-drop
      silenzioso (alcune righe scritte, altre troncate dal tetto senza avviso; Codex #281). Il
      tetto continua a limitare l'accumulo TRA messaggi distinti sul percorso single-row.

    Accounting guardrail per-riga (mirror del single-row): una riga `DAILY_LIMITED` NON è scritta →
    il suo consumo di tracker viene annullato (segnale ritentabile; il daily non aveva consumato
    slot, solo normalizzato il giorno). Se NESSUNA riga NUOVA è accettata (tutte duplicati/limiti),
    il CSV operativo NON viene toccato (come il single-row su DUPLICATE). In `DRY_RUN` non si scrive
    e i guardrail sono ripristinati. Se la scrittura fallisce, coda E guardrail tornano allo stato
    precedente. Per il single-row usare `commit_signal` (percorso legacy invariato)."""
    rows = list(rows or [])
    tracker_snap = tracker.state() if tracker is not None else None
    daily_snap = (daily.state() if (tracker is not None and daily is not None) else None)
    queue_snap = queue.state()
    overwrite = queue.mode == signal_queue.OVERWRITE_LAST
    queue.expire(now=now)

    # OVERWRITE_LAST: chiavi delle righe GIÀ ATTIVE (post-expire) calcolate sul testo CORRENTE.
    # Servono a riconoscere una riga `DUPLICATE` che è ANCORA attiva e va PRESERVATA nel blocco
    # (kyh #192): stesso testo → stesso `message_hash`, quindi la chiave per-riga della riga già
    # attiva coincide con quella della riga duplicata dell'istruzione corrente.
    active_keys_before = set()
    if overwrite:
        active_keys_before = {
            signal_dedupe.row_dedup_key(text, r) for r in queue.active_rows(now=now)
        }

    decisions = []
    new_rows = []       # righe NUOVE (WRITE) di QUESTO messaggio, effettivamente piazzate
    block = []          # OVERWRITE_LAST: blocco completo = righe nuove + duplicate ANCORA attive
    for row in rows:
        if tracker is None:
            # Chiamanti senza guardrail (test): ogni riga è NUOVA. In append usa `force=True`
            # (auto-raise: il blocco del messaggio non è spezzato dal tetto, #192).
            decisions.append(live_guard.WRITE)
            new_rows.append(row)
            block.append(row)
            if not overwrite:
                queue.add(row, now=now, force=True)
            continue
        key = signal_dedupe.row_dedup_key(text, row)
        row_tracker_snap = tracker.state()
        d = live_guard.evaluate(cfg, tracker, daily, text, dedup_key=key)
        decisions.append(d)
        if d == live_guard.WRITE:
            new_rows.append(row)
            block.append(row)
            if not overwrite:
                # Auto-raise del tetto (#192): `force=True` → la riga NUOVA di questo messaggio
                # multi entra sempre, il blocco coerente non è mai troncato dal tetto max_active.
                queue.add(row, now=now, force=True)
        elif d == live_guard.DUPLICATE:
            # OVERWRITE_LAST: un duplicato ANCORA attivo fa parte dell'istruzione corrente e va
            # PRESERVATO nel blocco (kyh #192), altrimenti `replace_block` lo perderebbe (A+B→B).
            # Un duplicato NON più attivo (scaduto/rimosso) resta scartato: la deduplica evita di
            # ripiazzare un segnale identico già visto entro la finestra.
            if overwrite and key in active_keys_before:
                block.append(row)
        elif d == live_guard.DAILY_LIMITED:
            # `daily.allow` ha rifiutato senza consumare slot ma `evaluate` ha registrato l'hash:
            # annulla SOLO il tracker (come single-row), non il daily (giorno normalizzato).
            tracker.restore_state(row_tracker_snap)

    # DRY_RUN: simulazione → NON scrivere il CSV operativo; ripristina coda E guardrail.
    if safety_guard.is_dry_run(cfg):
        queue.restore_state(queue_snap)
        if tracker is not None:
            tracker.restore_state(tracker_snap)
            if daily is not None and daily_snap is not None:
                daily.restore_state(daily_snap)
        return CommitResult(decision=live_guard.DRY_RUN, blocked_by_cap=False,
                            rows=[], write_error=None)

    # Nessuna riga NUOVA piazzata (tutte duplicati/limiti): NON toccare il CSV operativo (come il
    # single-row su DUPLICATE — XTrader non deve riconsumare righe identiche riscritte). Ripristina
    # la coda (annulla l'expire) così resta allineata al CSV ancora su disco.
    if not new_rows:
        queue.restore_state(queue_snap)
        return CommitResult(decision=_summary_decision(decisions, 0), blocked_by_cap=False,
                            rows=[], write_error=None)

    # OVERWRITE_LAST: sostituisci l'intero blocco attivo con TUTTE le righe dell'istruzione
    # (nuove + duplicate ancora attive), non solo le nuove — così A non viene perso (kyh #192).
    if overwrite:
        queue.replace_block(block, now=now)

    active = queue.active_rows()
    try:
        write_rows(active, path)
    except Exception as ex:   # noqa: BLE001 — riportato al chiamante, no crash
        queue.restore_state(queue_snap)
        if tracker is not None:
            tracker.restore_state(tracker_snap)
            if daily is not None and daily_snap is not None:
                daily.restore_state(daily_snap)
        return CommitResult(decision=live_guard.WRITE, blocked_by_cap=False,
                            rows=[], write_error=ex)

    return CommitResult(decision=_summary_decision(decisions, len(new_rows)),
                        blocked_by_cap=False, rows=active, write_error=None)
