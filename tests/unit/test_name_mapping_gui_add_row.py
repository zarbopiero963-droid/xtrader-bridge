"""Test della glue `NameMappingPanel._add_row` (issue #184 LOW — under-fill posizionale).

`name_mapping_gui` richiede `customtkinter` (un display) e NON è importabile headless;
qui stubbiamo SOLO la libreria GUI con classi reali vuote (subclassabili) così il modulo
si importa e possiamo esercitare il VERO metodo `_add_row` su un `self` finto, senza
creare alcun widget. Si verifica che l'aggiunta di una riga vuota chiami
`_append_row_widget()` **senza argomenti posizionali** (tutti i campi ai default), invece
dell'under-fill fragile `("", "", "")` su una firma a 5 parametri.
"""

import importlib
import sys
import types

import pytest


class _FakeCtkModule(types.ModuleType):
    """Finto `customtkinter`: ogni attributo richiesto è una classe reale vuota, così
    `class NameMappingPanel(ctk.CTkFrame)` e le istanze widget non rompono l'import."""

    def __getattr__(self, name):
        cls = type(name, (object,), {"__init__": lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls


@pytest.fixture()
def NameMappingPanel(monkeypatch):
    # Stub di customtkinter SOLO se assente (in CI lo è): non tocca un eventuale
    # customtkinter reale. monkeypatch ripristina sys.modules a fine test.
    try:
        import customtkinter  # noqa: F401
    except ModuleNotFoundError:
        monkeypatch.setitem(sys.modules, "customtkinter", _FakeCtkModule("customtkinter"))
    monkeypatch.delitem(sys.modules, "xtrader_bridge.name_mapping_gui", raising=False)
    mod = importlib.import_module("xtrader_bridge.name_mapping_gui")
    return mod.NameMappingPanel


def _fake_self():
    calls = []
    return types.SimpleNamespace(
        _current="profilo1",
        _append_row_widget=lambda *a, **k: calls.append((a, k)),
        _status=types.SimpleNamespace(
            configure=lambda **k: calls.append(("status", k))),
    ), calls


def test_add_row_aggiunge_riga_vuota_senza_argomenti_posizionali(NameMappingPanel):
    fake, calls = _fake_self()
    NameMappingPanel._add_row(fake)
    # esattamente una chiamata, SENZA argomenti posizionali (riga vuota ai default)
    assert calls == [((), {})]


def test_add_row_senza_profilo_non_aggiunge_riga(NameMappingPanel):
    fake, calls = _fake_self()
    fake._current = None                       # nessun profilo selezionato
    NameMappingPanel._add_row(fake)
    # niente _append_row_widget: solo il messaggio di stato
    assert all(c[0] == "status" for c in calls)
    assert not any(c == ((), {}) for c in calls)
