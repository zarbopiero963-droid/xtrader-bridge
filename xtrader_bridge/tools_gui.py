"""Finestra hub "🧰 Strumenti": raccoglie gli strumenti del bridge in schede.

Parte della consolidazione GUI (roadmap, Tappa 1): invece di N finestre separate
aperte da N pulsanti, gli strumenti vivono come schede di un'unica finestra.

`ToolsWindow` è DISACCOPPIATA dai singoli strumenti: riceve una lista di
`(titolo_scheda, factory)`, dove `factory(parent)` costruisce il pannello dentro la
scheda. Così questa finestra non conosce le callback/gli store dei singoli strumenti
— li cabla chi la apre (la GUI principale, che ha la config viva). Aggiungere uno
strumento = aggiungere una voce alla lista, senza toccare questa classe.

NB: modulo GUI, non testato in CI (richiede un display). La logica dei singoli
strumenti è coperta dai rispettivi test unitari. Verifica manuale su Windows.
"""

import customtkinter as ctk

from . import gui_utils


class ToolsWindow(ctk.CTkToplevel):
    """Finestra a schede che ospita i pannelli-strumento.

    Args:
        master: finestra padre.
        panels: lista di `(titolo, factory)`; `factory(parent)` ritorna un widget
            (tipicamente un `CTkFrame`) da mostrare nella scheda.
        initial: titolo della scheda da selezionare all'apertura (opzionale).
        title: titolo della finestra.
    """

    def __init__(self, master=None, panels=None, initial=None, title="🧰 Strumenti"):
        super().__init__(master)
        self.title(title)
        gui_utils.fit_to_screen(self, 1040, 720, 780, 480)
        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=8)
        for tab_title, factory in (panels or []):
            container = self._tabs.add(tab_title)
            factory(container).pack(fill="both", expand=True, padx=4, pady=4)
        if initial:
            try:
                self._tabs.set(initial)
            except Exception:               # noqa: BLE001 — titolo non valido: resta la 1ª scheda
                pass
