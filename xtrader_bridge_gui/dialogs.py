"""Modal dialogs and the separate dictionary windows."""

from __future__ import annotations

import customtkinter as ctk


def _center(win, parent, w, h):
    win.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
    except Exception:
        px = py = 0
        pw = ph = 600
    x = px + (pw - w) // 2
    y = py + (ph - h) // 3
    win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


class _Modal(ctk.CTkToplevel):
    def __init__(self, app, w, h):
        super().__init__(app)
        self.app = app
        self.c = app.c
        self.overrideredirect(False)
        self.configure(fg_color=self.c("win"))
        self.resizable(False, False)
        self.transient(app)
        _center(self, app, w, h)
        try:
            self.grab_set()
        except Exception:
            pass


class RealConfirm(_Modal):
    """Typed-`REALE` double confirmation (safety invariant §13.2)."""

    def __init__(self, app, on_confirm, on_cancel):
        super().__init__(app, 440, 300)
        self.title("Attivare la modalità REALE?")
        self.on_confirm, self.on_cancel = on_confirm, on_cancel
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(20, 10))
        badge = ctk.CTkFrame(head, width=38, height=38, corner_radius=10,
                             fg_color=self.c("danger_weak"))
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text="⚠", text_color=self.c("danger"),
                     font=app.kit.f_h2).pack(expand=True)
        tt = ctk.CTkFrame(head, fg_color="transparent")
        tt.pack(side="left", padx=11)
        ctk.CTkLabel(tt, text="Attivare la modalità REALE?", text_color=self.c("danger"),
                     font=app.kit.f_h2, anchor="w").pack(anchor="w")
        ctk.CTkLabel(tt, text="Doppia conferma richiesta", text_color=self.c("text3"),
                     font=app.kit.f_small, anchor="w").pack(anchor="w")

        ctk.CTkLabel(
            self, justify="left", wraplength=396, text_color=self.c("text2"), font=app.kit.f_small,
            text="Disattivando la simulazione, ogni segnale riconosciuto verrà scritto nel CSV "
                 "operativo e trasformato in una scommessa reale su XTrader."
        ).pack(anchor="w", padx=22)
        ctk.CTkLabel(self, text="Per confermare, digita la parola  REALE", text_color=self.c("text3"),
                     font=app.kit.f_small).pack(anchor="w", padx=22, pady=(12, 6))

        self.var = ctk.StringVar()
        self.entry = ctk.CTkEntry(self, textvariable=self.var, placeholder_text="Digita REALE",
                                  height=40, corner_radius=9, justify="center",
                                  font=app.kit.f_mono_b, fg_color=self.c("surface"),
                                  border_color=self.c("border"), text_color=self.c("text"))
        self.entry.pack(fill="x", padx=22)
        self.var.trace_add("write", lambda *_: self._sync())

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=18)
        row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(row, text="Annulla", command=self._cancel, height=38, corner_radius=9,
                      fg_color=self.c("surface"), text_color=self.c("text"),
                      hover_color=self.c("surface2"), border_width=1,
                      border_color=self.c("border"), font=app.kit.f_small_b).grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        self.ok = ctk.CTkButton(row, text="⏻  Attiva REALE", command=self._ok, height=38,
                                corner_radius=9, fg_color=self.c("danger"), text_color="#ffffff",
                                hover_color=self.c("danger_h"), font=app.kit.f_small_b)
        self.ok.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self._sync()
        self.after(120, self.entry.focus)

    def _ok_ready(self):
        return self.var.get().strip().upper() == "REALE"

    def _sync(self):
        ready = self._ok_ready()
        self.ok.configure(state="normal" if ready else "disabled")
        self.entry.configure(border_color=self.c("danger") if ready else self.c("border"))

    def _ok(self):
        if not self._ok_ready():
            return
        self.grab_release()
        self.destroy()
        self.on_confirm()

    def _cancel(self):
        self.grab_release()
        self.destroy()
        self.on_cancel()


class MultiConfirm(_Modal):
    def __init__(self, app, code, on_confirm):
        super().__init__(app, 440, 250)
        self.title("Attivare la modalità MULTI-segnale?")
        self.on_confirm = on_confirm
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(20, 10))
        badge = ctk.CTkFrame(head, width=38, height=38, corner_radius=10,
                             fg_color=self.c("warn_weak"))
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text="⚠", text_color=self.c("warn"), font=app.kit.f_h2).pack(expand=True)
        tt = ctk.CTkFrame(head, fg_color="transparent")
        tt.pack(side="left", padx=11)
        ctk.CTkLabel(tt, text="Attivare la modalità MULTI-segnale?", text_color=self.c("warn"),
                     font=app.kit.f_h2, anchor="w").pack(anchor="w")
        ctk.CTkLabel(tt, text="Più scommesse attive insieme", text_color=self.c("text3"),
                     font=app.kit.f_small, anchor="w").pack(anchor="w")

        ctk.CTkLabel(
            self, justify="left", wraplength=396, text_color=self.c("text2"), font=app.kit.f_small,
            text=f"Con {code} il bridge può tenere attive più righe/scommesse "
                 "contemporaneamente. Verifica il limite «Max segnali attivi»."
        ).pack(anchor="w", padx=22, pady=(0, 4))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=18, side="bottom")
        row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(row, text="No, resta a 1", command=self.destroy, height=38, corner_radius=9,
                      fg_color=self.c("surface"), text_color=self.c("text"),
                      hover_color=self.c("surface2"), border_width=1,
                      border_color=self.c("border"), font=app.kit.f_small_b).grid(
            row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(row, text="Sì, attiva", command=self._ok, height=38, corner_radius=9,
                      fg_color=self.c("warn"), text_color=self.c("warn_ink"),
                      hover_color=self.c("warn_h"), font=app.kit.f_small_b).grid(
            row=0, column=1, sticky="ew", padx=(5, 0))

    def _ok(self):
        self.grab_release()
        self.destroy()
        self.on_confirm()


class DictWindow(ctk.CTkToplevel):
    """Separate 'Dizionario mercati' / 'Dizionario nomi' window."""

    def __init__(self, app, kind):
        super().__init__(app)
        self.app, self.kit, self.c = app, app.kit, app.c
        is_mkt = kind == "markets"
        self.title("Dizionario mercati" if is_mkt else "Dizionario nomi")
        self.configure(fg_color=self.c("win"))
        _center(self, app, 900, 600)
        self.transient(app)

        head = self.kit.frame(self, fg="titlebar", corner=0, height=40)
        head.pack(fill="x")
        head.pack_propagate(False)
        self.kit.label(head, ("◎ " if is_mkt else "❒ ") +
                       ("Dizionario mercati" if is_mkt else "Dizionario nomi"),
                       color="text", font=self.kit.f_small_b).pack(side="left", padx=13)
        self.kit.button(head, "✕", kind="titlebar", width=30, height=28, command=self.destroy,
                        font=self.kit.f_small_b).pack(side="right", padx=6)

        body = self.kit.frame(self, fg="win", corner=0)
        body.pack(fill="both", expand=True)
        desc = ("Legge il mercato da una posizione precisa del messaggio: «Inizia dopo» / "
                "«Finisce prima» ritagliano il campo, e se vi compare il «Testo mercato» imposta "
                "Mercato/Selezione dal Catalogo. Seleziona i profili nel Parser Personalizzato."
                if is_mkt else
                "Associa i nomi squadra/selezione del canale al nome atteso da Betfair/XTrader "
                "per profilo. Seleziona i profili nel Parser Personalizzato.")
        self.kit.label(body, desc, color="text3", font=self.kit.f_small, justify="left",
                       wraplength=840).pack(anchor="w", padx=20, pady=(16, 12))

        prof = ctk.CTkFrame(body, fg_color="transparent")
        prof.pack(fill="x", padx=20, pady=(0, 14))
        self.kit.label(prof, "Profilo:", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.option(prof, ["(nessun profilo)"], width=200).pack(side="left", padx=8)
        for label, kind_b in (("＋ Nuovo", "accent"), ("✎ Rinomina", "accent"), ("🗑 Elimina", "danger")):
            self.kit.button(prof, label, kind=kind_b, width=110, height=32,
                            font=self.kit.f_small).pack(side="left", padx=(0, 6))

        table = self.kit.frame(body, fg="surface", border="border", bw=1, corner=10)
        table.pack(fill="both", expand=True, padx=20)
        self.kit.label(table, "Righe del profilo", color="text2", font=self.kit.f_tiny_b,
                       fg_color="titlebar", corner_radius=0).pack(fill="x")
        cols = (["Inizia dopo", "Finisce prima", "Testo mercato", "Mercato (catalogo)",
                 "Selezione (catalogo)"] if is_mkt else
                ["Nome dal canale", "Nome Betfair/XTrader", "Provider"])
        hdr = ctk.CTkFrame(table, fg_color="transparent")
        hdr.pack(fill="x", padx=1, pady=1)
        for i, col in enumerate(cols):
            hdr.grid_columnconfigure(i, weight=1, uniform="dc")
            self.kit.label(hdr, col, color="text3", font=self.kit.f_micro_b, anchor="w").grid(
                row=0, column=i, sticky="w", padx=10, pady=8)
        self.kit.label(table, "Nessun profilo. Crea un profilo con «Nuovo».", color="text3",
                       font=self.kit.f_small).pack(pady=32)

        foot = self.kit.frame(self, fg="titlebar", corner=0)
        foot.pack(fill="x")
        self.kit.button(foot, "＋ Aggiungi riga", kind="accent", width=140,
                        font=self.kit.f_small_b).pack(side="left", padx=20, pady=12)
        self.kit.button(foot, "Salva profilo", kind="success", width=140,
                        font=self.kit.f_small_b).pack(side="right", padx=20, pady=12)
