"""Test della logica UX della modalità REALE (`xtrader_bridge.real_mode`).

Logica pura, headless: conferma alla transizione sim→reale, frase di conferma,
testo del banner persistente, evento di audit ed estrazione per l'export.
"""

from xtrader_bridge import real_mode as rm

SIM = {"dry_run": True}
REAL = {"dry_run": False}


def test_requires_confirmation_solo_su_transizione_sim_to_real():
    assert rm.requires_confirmation(SIM, REAL) is True       # sim → reale: conferma
    assert rm.requires_confirmation(REAL, REAL) is False     # già reale: niente conferma
    assert rm.requires_confirmation(SIM, SIM) is False       # resta sim
    assert rm.requires_confirmation(REAL, SIM) is False      # reale → sim: niente conferma


def test_requires_confirmation_default_sim_quando_campo_assente():
    # Config senza `dry_run` = simulazione (default sicuro). Passare a reale chiede conferma.
    assert rm.requires_confirmation({}, REAL) is True
    assert rm.requires_confirmation({}, {}) is False


def test_confirmation_ok():
    assert rm.confirmation_ok("REALE") is True
    assert rm.confirmation_ok("reale") is True               # case-insensitive
    assert rm.confirmation_ok("  Reale  ") is True           # trim
    assert rm.confirmation_ok("REAL") is False               # parola sbagliata
    assert rm.confirmation_ok("") is False
    assert rm.confirmation_ok(None) is False                 # dialog annullato


def test_banner_text_solo_in_reale():
    assert rm.banner_text(SIM) is None                       # simulazione → niente banner
    assert rm.banner_text({}) is None                        # default sim
    txt = rm.banner_text(REAL)
    assert txt is not None and "REALE" in txt.upper()


def test_enabled_message_contiene_marker():
    msg = rm.enabled_message()
    assert rm.AUDIT_MARKER in msg
    assert "reali" in msg.lower()


def test_extract_audit_lines():
    log = (
        "[10:00:00] 🚀 Bridge avviato!\n"
        f"[10:00:01] ⚠️ {rm.AUDIT_MARKER}: modalità REALE attivata (confermata) — ...\n"
        "[10:01:00] 📱 Segnale: ...\n"
        f"[11:00:00] {rm.AUDIT_MARKER}: modalità REALE attivata (confermata) — ...\n"
    )
    out = rm.extract_audit_lines(log)
    assert len(out) == 2
    assert all(rm.AUDIT_MARKER in ln for ln in out)
    assert "🚀 Bridge avviato" not in "\n".join(out)         # solo le righe di audit
    assert rm.extract_audit_lines("") == []
    assert rm.extract_audit_lines(None) == []
