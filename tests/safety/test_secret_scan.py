"""Test hard dello scanner segreti condiviso (`tools/secret_scan.sh`) — audit #105 / #153 H3.

Esercita lo script reale via subprocess: deve uscire 1 sui segreti noti (token Telegram,
chiave privata PEM, AWS key id) stampando SOLO il path (mai il valore), e 0 su file puliti.

I segreti fittizi sono costruiti per **concatenazione** così il sorgente di questo test NON
contiene il pattern in chiaro (altrimenti il gate `forbidden-files` lo segnalerebbe).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "tools" / "secret_scan.sh"

# Segreti fittizi spezzati: a runtime sono validi per il pattern, in sorgente no.
FAKE_TELEGRAM = "123456789" + ":" + ("A" * 35)
FAKE_PEM = "-----BEGIN " + "RSA PRIVATE " + "KEY-----"
FAKE_AWS = "AKI" + "A" + ("0" * 16)

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not SCANNER.exists(),
    reason="bash o tools/secret_scan.sh non disponibili",
)


def _run(*paths):
    return subprocess.run(
        ["bash", str(SCANNER), *map(str, paths)],
        capture_output=True, text=True,
    )


def test_file_pulito_esce_zero(tmp_path):
    f = tmp_path / "clean.txt"
    f.write_text("nessun segreto qui\nsolo testo\n")
    r = _run(f)
    assert r.returncode == 0
    assert "OK" in r.stdout


@pytest.mark.parametrize("secret", [FAKE_TELEGRAM, FAKE_PEM, FAKE_AWS])
def test_segreto_noto_esce_uno_e_non_stampa_il_valore(tmp_path, secret):
    f = tmp_path / "leak.txt"
    f.write_text(f"config = {secret}\n")
    r = _run(f)
    assert r.returncode == 1, f"atteso fallimento per {secret!r}"
    # Il path è segnalato...
    assert "leak.txt" in (r.stdout + r.stderr)
    # ...ma il VALORE del segreto non deve mai comparire nell'output.
    assert secret not in (r.stdout + r.stderr)


def test_misto_pulito_e_segreto_fallisce(tmp_path):
    clean = tmp_path / "ok.txt"
    clean.write_text("tutto bene\n")
    leak = tmp_path / "bad.txt"
    leak.write_text(f"token={FAKE_TELEGRAM}\n")
    r = _run(clean, leak)
    assert r.returncode == 1
    assert "bad.txt" in (r.stdout + r.stderr)
    assert FAKE_TELEGRAM not in (r.stdout + r.stderr)


def test_nessun_argomento_su_repo_pulito_esce_zero():
    # Senza argomenti scansiona i file tracciati: il repo non contiene segreti noti.
    r = subprocess.run(
        ["bash", str(SCANNER)], cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
