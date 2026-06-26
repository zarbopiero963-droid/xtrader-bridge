"""Gate di sicurezza della build EXE personale (issue #86 PR-P13).

La build Windows deve produrre **solo** l'EXE personale del bridge, senza includere segreti
né certificati e senza un secondo «Admin EXE». La compilazione vera (PyInstaller su Windows)
NON gira in questa CI Linux: qui si verifica in modo deterministico e offline che i
**workflow** rispettino le regole non negoziabili dell'issue:

- una sola compilazione PyInstaller per workflow (nessun Admin/secondo EXE);
- nessun `--add-data`/`--add-binary` che includa certificati, chiavi, `.env`, `config.json`,
  DB locale o token: nel bundle è ammesso **solo** `data/dizionario_xtrader.csv` (sorgente
  esatta, mai una cartella che trascinerebbe tutto `data/`);
- i test girano PRIMA di compilare l'EXE (una build non parte su codice rotto);
- `data/` non contiene file sensibili che `--collect-all`/`--add-data` potrebbero includere.

I controlli sul comando di build si applicano a **ogni** workflow che contiene una reale
invocazione `pyinstaller` (non solo `build.yaml`): oggi `build.yaml` e
`merge-simulation-hard.yml`, e automaticamente qualunque nuovo workflow di build aggiunto in
futuro (Codex).
"""

import os
import re

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BUILD_YAML = os.path.join(_REPO_ROOT, ".github", "workflows", "build.yaml")
_WORKFLOWS_DIR = os.path.join(_REPO_ROOT, ".github", "workflows")
_DATA_DIR = os.path.join(_REPO_ROOT, "data")

# L'UNICO file di progetto ammesso nel bundle dell'EXE (sorgente --add-data normalizzata).
_ALLOWED_BUNDLE_SRC = "data/dizionario_xtrader.csv"

# Estensioni/nomi vietati nel bundle dell'EXE (segreti, credenziali, artefatti locali).
_FORBIDDEN_BUNDLE = re.compile(
    r"\.(crt|pem|key|env|p12|pfx|db|sqlite|sqlite3|log|zip)\b|config\.json|secret|token",
    re.IGNORECASE)

# Riga che inizia con `pyinstaller` = REALE invocazione di build (non un commento o un
# `pip install ... pyinstaller`).
_PYINSTALLER_LINE = re.compile(r"(?m)^\s*pyinstaller\b")


def _workflow_files():
    return [os.path.join(_WORKFLOWS_DIR, n) for n in sorted(os.listdir(_WORKFLOWS_DIR))
            if n.endswith((".yml", ".yaml"))]


def _build_yaml() -> str:
    with open(_BUILD_YAML, "r", encoding="utf-8") as fh:
        return fh.read()


def _build_workflows():
    """`(nome, testo)` per OGNI workflow con una reale invocazione `pyinstaller`."""
    out = []
    for path in _workflow_files():
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if _PYINSTALLER_LINE.search(text):
            out.append((os.path.basename(path), text))
    return out


def test_build_yaml_esiste():
    assert os.path.isfile(_BUILD_YAML), "manca .github/workflows/build.yaml"


def test_build_workflows_rilevati():
    # Il gate deve coprire OGNI workflow che compila l'EXE. Verifichiamo che la scoperta
    # automatica trovi (almeno) i due build noti, così un nuovo workflow di build non passa
    # inosservato ai controlli sotto.
    names = {name for name, _ in _build_workflows()}
    assert "build.yaml" in names, "build.yaml non rilevato come workflow di build"
    assert "merge-simulation-hard.yml" in names, \
        "merge-simulation-hard.yml ha un pyinstaller non coperto dal gate"


def test_una_sola_compilazione_pyinstaller():
    # In OGNI workflow di build: esattamente UNA invocazione PyInstaller (niente secondo
    # EXE, es. Admin) e `--onefile` (EXE singolo personale).
    builds = _build_workflows()
    assert builds, "nessun workflow di build trovato"
    for name, text in builds:
        n = len(_PYINSTALLER_LINE.findall(text))
        assert n == 1, f"{name}: attesa UNA sola build PyInstaller, trovate {n}"
        assert "--onefile" in text, f"{name}: build non --onefile"


def test_nessun_admin_exe():
    # Nessun riferimento a una build/EXE «Admin» in alcun workflow.
    for path in _workflow_files():
        with open(path, "r", encoding="utf-8") as fh:
            low = fh.read().casefold()
        assert "admin exe" not in low
        assert "admin.exe" not in low
        # niente pyinstaller che nomina un target "admin"
        assert not re.search(r"pyinstaller[^\n]*admin", low)


def test_adddata_solo_il_dizionario():
    # In OGNI workflow di build, ogni --add-data "SORG;DEST" deve avere come SORGENTE
    # ESATTAMENTE il dizionario ufficiale. Non basta "se è un .csv allora dev'essere il
    # dizionario": una sorgente-cartella tipo `data;data` non finisce in `.csv`, salterebbe
    # l'allowlist e impacchetterebbe TUTTO `data/` (Codex). Si esige quindi la sorgente
    # esatta, qualunque essa sia.
    builds = _build_workflows()
    assert builds, "nessun workflow di build trovato"
    for name, text in builds:
        entries = re.findall(r'--add-data\s+"([^"]+)"', text)
        assert entries, f"{name}: atteso almeno un --add-data (il dizionario)"
        for entry in entries:
            # Separatore PyInstaller su Windows = `;` (NON splittare su `:`, troncherebbe
            # un eventuale path con drive letter `C:\...`).
            src = entry.split(";", 1)[0].strip().replace("\\", "/")
            assert not _FORBIDDEN_BUNDLE.search(src), \
                f"{name}: --add-data include un file vietato: {src!r}"
            assert src == _ALLOWED_BUNDLE_SRC, \
                f"{name}: nel bundle è ammesso SOLO {_ALLOWED_BUNDLE_SRC}, non {src!r}"


def test_nessun_add_binary_di_certificati():
    # In OGNI workflow di build: nessun --add-binary che trascini cert/chiavi nell'EXE.
    for name, text in _build_workflows():
        for entry in re.findall(r'--add-binary\s+"([^"]+)"', text):
            assert not _FORBIDDEN_BUNDLE.search(entry), \
                f"{name}: --add-binary include un file vietato: {entry!r}"


def test_test_eseguiti_prima_della_build():
    # In OGNI workflow di build, i test devono precedere la compilazione: si confronta lo
    # step REALE `python -m pytest` con la REALE invocazione `^pyinstaller`, NON un semplice
    # substring "pytest"/"pyinstaller" (un commento che cita entrambe le parole soddisferebbe
    # falsamente il gate). Codex.
    builds = _build_workflows()
    assert builds, "nessun workflow di build trovato"
    for name, text in builds:
        i_pytest = text.find("python -m pytest")
        m_build = _PYINSTALLER_LINE.search(text)
        assert i_pytest != -1, f"{name}: manca lo step reale dei test (`python -m pytest`)"
        assert m_build is not None, f"{name}: manca la reale invocazione `pyinstaller`"
        assert i_pytest < m_build.start(), \
            f"{name}: i test devono girare PRIMA della build dell'EXE"


def test_data_dir_senza_file_sensibili():
    # La cartella bundle-abile `data/` non deve contenere segreti/cert/DB (li includerebbe
    # --add-data/--collect-all). Scansione RICORSIVA (os.walk): un file annidato come
    # `data/certs/client.key` o `data/parsers/.env` verrebbe impacchettato se `data/` fosse
    # bundlata come cartella, e `os.listdir` sul solo primo livello non lo vedrebbe (Codex).
    assert os.path.isdir(_DATA_DIR)
    found_dizionario = False
    for root, _dirs, files in os.walk(_DATA_DIR):
        for n in files:
            if n == "dizionario_xtrader.csv":
                found_dizionario = True
            rel = os.path.relpath(os.path.join(root, n), _DATA_DIR)
            assert not _FORBIDDEN_BUNDLE.search(n), f"file sensibile in data/: {rel!r}"
    assert found_dizionario, "manca data/dizionario_xtrader.csv"


def test_artifact_e_release_solo_un_exe():
    # L'upload artifact (`path:`) E la release (`files:`, softprops/action-gh-release) di
    # build.yaml devono pubblicare ESATTAMENTE un singolo .exe da dist/, non cartelle e non
    # un secondo eseguibile: prima il gate leggeva solo `path:` (lato release non verificato)
    # e accettava "almeno un" exe (un secondo dist/Admin.exe sarebbe passato). Codex.
    text = _build_yaml()
    artifact_exes = [p for p in re.findall(r"(?m)^\s*path:\s*(\S+)", text)
                     if p.lower().endswith(".exe")]
    release_exes = [p for p in re.findall(r"(?m)^\s*files:\s*(\S+)", text)
                    if p.lower().endswith(".exe")]
    assert len(artifact_exes) == 1, \
        f"atteso ESATTAMENTE un EXE nell'upload artifact, trovati {artifact_exes}"
    assert len(release_exes) == 1, \
        f"atteso ESATTAMENTE un EXE nella release, trovati {release_exes}"
    for p in artifact_exes + release_exes:
        assert p.startswith("dist/"), f"path EXE inatteso: {p!r}"
    # Difesa in profondità su TUTTI i workflow di build: qualunque `dist/*.exe` referenziato
    # (upload, release, copia, ecc.) deve essere SOLO quello personale — mai un secondo
    # eseguibile (es. dist/Admin.exe). Un workflow può non nominare affatto dist/ (PyInstaller
    # ci scrive implicitamente): l'unicità della build è già garantita da
    # test_una_sola_compilazione_pyinstaller, qui blocchiamo solo un EXE estraneo.
    for name, wf_text in _build_workflows():
        foreign = [e for e in re.findall(r"dist/(\S+\.exe)", wf_text)
                   if e != "XTrader-Signal-Bridge.exe"]
        assert not foreign, f"{name}: referenziato un secondo EXE inatteso: {foreign}"
