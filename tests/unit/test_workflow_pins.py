"""Hardening supply-chain (PR dedicato): ogni GitHub Action nei workflow deve
essere fissata a uno SHA di commit immutabile (40 hex), non a un tag mutabile.

Un tag come `@v4` può essere ri-puntato a un commit diverso (retargeting), quindi
non è riproducibile/affidabile. Questo test fallisce se un `uses:` torna a un tag,
così la regola resta valida nel tempo (zizmor `unpinned-uses`)."""

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.y*ml"))

# `uses: owner/repo@<ref>` (ignora i `uses:` locali `./...` e i docker `docker://`).
_USES_RE = re.compile(r"uses:\s*([^\s@]+)@([^\s#]+)")
# `re.IGNORECASE`: uno SHA Git può comparire in maiuscolo/misto ed è comunque un
# pin valido; senza ignorecase il test lo rigetterebbe per errore (falso positivo).
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _external_uses():
    for wf in WORKFLOWS:
        text = wf.read_text(encoding="utf-8")
        for action, ref in _USES_RE.findall(text):
            if action.startswith("./") or action.startswith("docker://"):
                continue
            yield wf.name, action, ref


def test_ci_presenti():
    assert WORKFLOWS, "nessun workflow trovato in .github/workflows"


@pytest.mark.parametrize("wf,action,ref", list(_external_uses()),
                         ids=lambda v: v if isinstance(v, str) else "")
def test_action_pinnata_a_sha(wf, action, ref):
    assert _SHA_RE.match(ref), (
        f"{wf}: {action}@{ref} non è fissata a uno SHA di commit (40 hex). "
        f"Usa `uses: {action}@<sha>  # <versione>`.")
