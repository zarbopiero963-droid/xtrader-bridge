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
  guardrail riflette SOLO i WRITE reali: DAILY_LIMITED e DRY_RUN, che in `evaluate` avevano
  consumato dedupe/tetto pur senza scrivere, vengono **annullati** (rollback). Così la
  simulazione non consuma il tetto reale e un segnale soppresso resta ritentabile, senza
  rischio di doppia scommessa (#184 low-tracker-nonwrite).
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

from . import live_guard


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
    elif tracker is not None and decision in (live_guard.DAILY_LIMITED, live_guard.DRY_RUN):
        # Esito non-WRITE che però aveva CONSUMATO stato dei guardrail dentro `evaluate`:
        # DAILY_LIMITED ha registrato l'hash nel tracker; DRY_RUN ha registrato l'hash E
        # incrementato il tetto giornaliero — per un segnale MAI scritto. Rollback
        # (#184 low-tracker-nonwrite): lo stato dei guardrail (dedupe + tetto) riflette SOLO i
        # WRITE reali. Così la simulazione non consuma il tetto/dedupe reale e un segnale soppresso
        # resta ritentabile (niente bet persa dopo il reset giornaliero), SENZA rischio di doppia
        # scommessa: un duplicato reale viene comunque soppresso perché il suo hash nasce da un
        # WRITE. DUPLICATE/RATE_LIMITED non vengono toccati: `register` non aveva aggiunto nulla.
        tracker.restore_state(tracker_snap)
        if daily is not None and daily_snap is not None:
            daily.restore_state(daily_snap)

    return CommitResult(decision=decision, blocked_by_cap=blocked_by_cap,
                        rows=rows, write_error=write_error)
