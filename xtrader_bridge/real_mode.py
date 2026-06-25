"""UX della modalità REALE (disattivazione DRY_RUN) — logica pura, testabile.

Passare da **simulazione** (DRY_RUN) a **REALE** è la transizione più pericolosa del
bridge: oltre quel punto i segnali validi vengono scritti nel CSV operativo e XTrader
può piazzare scommesse **vere**. Questo modulo concentra la logica (decisioni + testo)
che la GUI usa per rendere la transizione "frictionful" e tracciabile, **senza**
dipendere da GUI/Telegram/CSV (testabile headless):

- `requires_confirmation(old_cfg, new_cfg)`: True quando si passa da simulazione a reale
  → la GUI chiede una conferma esplicita (doppia conferma: spunta + frase digitata).
- `CONFIRM_PHRASE` / `confirmation_ok(typed)`: la frase che l'utente deve digitare per
  confermare l'attivazione.
- `banner_text(cfg)`: testo del banner rosso **persistente** quando il bridge è in reale
  (``None`` in simulazione → niente banner).
- `AUDIT_MARKER` / `enabled_message()`: la riga di audit `REAL_MODE_ENABLED …` loggata
  all'attivazione (il timestamp lo aggiunge il sink di logging).
- `extract_audit_lines(text)`: estrae da un log le righe di audit della modalità reale,
  per l'export.

NB: la **persistenza** del flag `dry_run` resta invariata (scelta del proprietario): la
modalità reale, una volta confermata e salvata, resta tra i riavvii. Questo modulo
aggiunge solo attrito/visibilità all'attivazione, non cambia dove vive lo stato.
"""

from . import safety_guard

# Frase che l'utente deve digitare per confermare l'attivazione della modalità reale.
# Confronto case-insensitive + trim (vedi `confirmation_ok`).
CONFIRM_PHRASE = "REALE"

# Marcatore testuale dell'evento di audit nei log (stabile: usato anche dall'export).
AUDIT_MARKER = "REAL_MODE_ENABLED"


def requires_confirmation(old_cfg, new_cfg) -> bool:
    """``True`` se `new_cfg` attiva la modalità REALE mentre `old_cfg` era in
    **simulazione** (transizione sim→reale). Stesso stato, o reale→sim, → ``False``:
    la conferma serve solo nel momento pericoloso dell'**attivazione**."""
    return safety_guard.is_dry_run(old_cfg) and not safety_guard.is_dry_run(new_cfg)


def confirmation_ok(typed) -> bool:
    """``True`` se il testo digitato corrisponde a `CONFIRM_PHRASE` (trim,
    case-insensitive). ``None``/vuoto/diverso → ``False`` (attivazione annullata)."""
    return str(typed or "").strip().upper() == CONFIRM_PHRASE


def banner_text(cfg):
    """Testo del banner rosso da mostrare in modo **persistente** quando il bridge è in
    REALE; ``None`` in simulazione (nessun banner)."""
    if safety_guard.is_dry_run(cfg):
        return None
    return ("⚠️ MODALITÀ REALE ATTIVA — i segnali validi vengono scritti nel CSV "
            "operativo e XTrader può piazzare scommesse REALI.")


def enabled_message() -> str:
    """Messaggio di audit per l'attivazione della modalità reale (senza timestamp: lo
    aggiunge il sink di logging). Contiene `AUDIT_MARKER` così `extract_audit_lines` lo
    ritrova. Nessun dato sensibile."""
    return (f"{AUDIT_MARKER}: modalità REALE attivata (confermata) — da ora XTrader "
            "può piazzare scommesse reali.")


def extract_audit_lines(text) -> list:
    """Righe di `text` (contenuto di uno o più log) che contengono l'evento di audit
    della modalità reale (`AUDIT_MARKER`), nell'ordine originale. Per l'export."""
    return [ln for ln in str(text or "").splitlines() if AUDIT_MARKER in ln]
