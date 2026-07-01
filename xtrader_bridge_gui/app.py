"""Main window for the redesigned XTrader Signal Bridge."""

from __future__ import annotations

import datetime
import random

import customtkinter as ctk

from .ui import Kit, StatusDot, TabBar
from .glyphs import Glyph

APP_TITLE = "XTrader Signal Bridge"
VERSION = "0.1.0"

STATUS = {
    "offline": {"label": "OFFLINE", "c": "danger", "bg": "danger_weak", "pulse": None},
    "active": {"label": "ATTIVO", "c": "success", "bg": "success_weak", "pulse": 1600},
    "reconnect": {"label": "RICONNESSIONE…", "c": "warn", "bg": "warn_weak", "pulse": 800},
}
COUNTER_META = [
    ("received", "Ricevuti", "info"), ("written", "Scritti", "success"),
    ("discarded", "Scartati", "warn"), ("duplicate", "Duplicati", "text2"),
    ("limited", "Limitati", "warn"), ("dry_run", "Simulati", "info"),
    ("errors", "Errori", "danger"),
]


class App(ctk.CTk):
    def __init__(self, smoke=False):
        super().__init__()
        self.smoke = smoke
        ctk.set_appearance_mode("dark")
        ctk.set_widget_scaling(1.0)
        self.title(f"{APP_TITLE} v{VERSION}")
        self.geometry("812x904")
        self.minsize(760, 660)

        self.kit = Kit(self)
        self.configure(fg_color=self.kit.color("desk"))
        self.kit.add_dynamic(lambda: self.configure(fg_color=self.kit.color("desk")))

        # ── shared state ─────────────────────────────────────────────────
        self.status = "offline"
        self.mode = "sim"                     # sim | real
        self.queue_mode = "OVERWRITE_LAST"
        self.max_active = 2
        self.active_rows = 0
        self.counters = {k: 0 for k, _, _ in COUNTER_META}
        self.logs = []
        self.chats = [
            {"name": "VIP Signals Calcio", "id": "-1001234567890"},
            {"name": "Tennis Alerts", "id": "-1005544332211"},
        ]
        self.providers = ["test", "TelegramBot"]
        self.team_map = [
            {"country": "", "betfair": "Inter Milan", "provider": "Inter"},
            {"country": "", "betfair": "Juventus", "provider": "Juve"},
            {"country": "", "betfair": "Manchester Utd", "provider": "Man Utd"},
        ]
        self.market_map = [
            {"from": "over 2.5", "to": "OVER_UNDER_25"},
            {"from": "1x2", "to": "MATCH_ODDS"},
            {"from": "gg", "to": "BOTH_TEAMS_TO_SCORE"},
        ]
        self.last_signal = self.last_message = self.last_csv = self.last_error = "—"
        self._tick = None
        self._recon = None
        self._pulse_job = None
        self._toast_job = None
        self.tools_win = None

        self.cfg_tab = "gen"
        self.mon_tab = "chats"

        self._build()
        self._refresh_all()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── small utils ──────────────────────────────────────────────────────
    def c(self, key):
        return self.kit.color(key)

    def _now(self):
        return datetime.datetime.now().strftime("%H:%M:%S")

    def log(self, level, msg, color="text2"):
        self.logs.insert(0, {"time": self._now(), "level": level, "msg": msg, "color": color})
        self.logs = self.logs[:80]
        self._render_logs()

    def toast(self, text):
        self._toast_lbl.configure(text="   " + text + "   ")
        self._toast_lbl.place(relx=0.5, rely=1.0, y=-26, anchor="s")
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(2400, self._toast_lbl.place_forget)

    # ══════════════════════════════════════════════════════════════════════
    #  BUILD
    # ══════════════════════════════════════════════════════════════════════
    def _build(self):
        self.body = ctk.CTkScrollableFrame(self, corner_radius=0)
        self.body.configure(fg_color=self.c("win"))
        self.kit.add_dynamic(lambda: self.body.configure(fg_color=self.c("win")))
        self.body.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_hero()
        self._build_real_banner()
        self._build_config_card()
        self._build_action_bar()
        self._build_warn_banner()
        self._build_monitor_card()

        # toast (hidden until used)
        self._toast_lbl = self.kit.label(self, "", color="win", font=self.kit.f_small_b,
                                         corner_radius=10, fg_color="text", height=34)

    # ── hero header ──────────────────────────────────────────────────────
    def _build_hero(self):
        hero = self.kit.frame(self.body, fg="hero", border="accent_soft", bw=1, corner=11)
        hero.pack(fill="x", padx=15, pady=(12, 0))
        inner = ctk.CTkFrame(hero, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=13)

        logo = self.kit.frame(inner, fg="accent", corner=9, width=34, height=34)
        logo.pack(side="left")
        logo.pack_propagate(False)
        Glyph(logo, self.kit, "bridge", size=22, color="#ffffff", bg="accent").pack(expand=True)

        self.kit.label(inner, APP_TITLE, color="accent", font=self.kit.f_h1).pack(side="left", padx=12)

        # right cluster (packed right-to-left)
        self.theme_btn = ctk.CTkFrame(inner, width=30, height=30, corner_radius=8,
                                      border_width=1, cursor="hand2")
        self.kit.reg(self.theme_btn, fg_color="surface", border_color="border")
        self.theme_btn.pack(side="right")
        self.theme_btn.pack_propagate(False)
        self.theme_glyph = Glyph(self.theme_btn, self.kit, "sun", size=17,
                                 color="text2", bg="surface")
        self.theme_glyph.pack(expand=True)
        for w in (self.theme_btn, self.theme_glyph):
            w.bind("<Button-1>", lambda e: self.toggle_theme())

        self.pill = ctk.CTkFrame(inner, height=28, corner_radius=20)
        self.pill.pack(side="right", padx=(0, 10))
        self.pill.pack_propagate(False)
        self.pill_dot = StatusDot(self.pill, self.kit, size=9)
        self.pill_dot.pack(side="left", padx=(12, 6), pady=8)
        self.pill_lbl = ctk.CTkLabel(self.pill, text="OFFLINE", font=self.kit.f_tiny_b)
        self.pill_lbl.pack(side="left", padx=(0, 12))

        self.active_lbl = self.kit.label(inner, "Righe attive: 0/2", color="text2",
                                        font=self.kit.f_small)
        self.active_lbl.pack(side="right", padx=(0, 12))

    def _build_real_banner(self):
        self.real_banner = self.kit.frame(self.body, fg="danger", corner=9)
        lbl = ctk.CTkLabel(
            self.real_banner, text_color="#ffffff", font=self.kit.f_small_b, justify="left",
            text="  ⚠  MODALITÀ REALE ATTIVA — i segnali diventano scommesse reali sul CSV operativo.")
        lbl.pack(anchor="w", padx=13, pady=9)
        # packed/unpacked in refresh

    def _build_warn_banner(self):
        self.warn_banner = self.kit.frame(self.body, fg="warn_weak",
                                          border="warn", bw=1, corner=9)
        self.kit.label(
            self.warn_banner, color="warn", font=self.kit.f_small_b, justify="left",
            text="  ⚠  Nessuna chat configurata — il bridge non si avvierà finché non "
                 "imposti una Chat ID o una Chat sorgente.").pack(anchor="w", padx=13, pady=10)

    # ── config card ──────────────────────────────────────────────────────
    def _build_config_card(self):
        card = self.kit.frame(self.body, fg="surface", border="border", bw=1)
        card.pack(fill="x", padx=15, pady=(12, 0))
        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.pack(pady=(10, 0))
        self.cfg_tabs = TabBar(bar, self.kit,
                               [("gen", "Generale"), ("rec", "Riconoscimento"),
                                ("safe", "Sicurezza"), ("conf", "Conferme XTrader")],
                               "gen", self._set_cfg_tab)
        self.cfg_tabs.pack()
        holder = ctk.CTkFrame(card, fg_color="transparent")
        holder.pack(fill="x", padx=15, pady=16)
        self.cfg_holder = holder
        self.cfg_frames = {
            "gen": self._cfg_generale(holder),
            "rec": self._cfg_riconoscimento(holder),
            "safe": self._cfg_sicurezza(holder),
            "conf": self._cfg_conferme(holder),
        }
        self._set_cfg_tab("gen")

    def _cfg_generale(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        fields = [
            ("Bot Token", "", "incolla il token del bot", True),
            ("Chat ID", "", "es. -1001234567890", False),
            ("CSV Path", "C:\\XTrader\\segnali.csv", "", False),
            ("Timeout (sec)", "90", "", False),
            ("Provider", "TelegramBot", "", False),
        ]
        for i, (label, val, ph, secret) in enumerate(fields):
            self.kit.label(f, label, color="text2", font=self.kit.f_small).grid(
                row=i, column=0, sticky="w", padx=(0, 14), pady=5)
            var = ctk.StringVar(value=val)
            e = self.kit.entry(f, textvariable=var, placeholder=ph, mono=True, field="win")
            if secret:
                e.configure(show="•")
            e.grid(row=i, column=1, sticky="ew", pady=5)
        return f

    def _cfg_riconoscimento(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        self.kit.label(f, "Modalità riconoscimento", color="text2",
                       font=self.kit.f_small).grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.kit.option(f, ["NAME_ONLY — riconosci per nomi (Evento / Mercato / Selezione)",
                            "ID_ONLY — riconosci per ID Betfair", "BOTH — nomi + ID"],
                        field="win", width=420).grid(row=0, column=1, sticky="w", pady=2)
        note = self.kit.frame(f, fg="info_weak", border="info", bw=1, corner=9)
        note.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(13, 0))
        self.kit.label(
            note, color="text2", font=self.kit.f_small, justify="left", wraplength=560,
            text="La quota obbligatoria è governata dalla casella «Obblig.» sulla riga Price "
                 "di ogni Parser Personalizzato, non da un interruttore globale."
        ).pack(anchor="w", padx=13, pady=11)
        return f

    def _cfg_sicurezza(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        self.sim_var = ctk.BooleanVar(value=True)
        self.dry_frame = self.kit.frame(f, fg="warn_weak", border="warn", bw=1, corner=9)
        self.dry_frame.grid(row=0, column=0, sticky="ew", pady=(0, 11))
        self.dry_check = self.kit.check(
            self.dry_frame, variable=self.sim_var, command=self.toggle_dry, color="text",
            text="  Simulazione (DRY_RUN): NON scrive il CSV operativo")
        self.dry_check.configure(font=self.kit.f_small_b)
        self.dry_check.pack(anchor="w", padx=13, pady=11)

        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew")
        grid.grid_columnconfigure(1, weight=1)
        self.kit.label(grid, "Limite segnali al giorno", color="text2",
                       font=self.kit.f_small).grid(row=0, column=0, sticky="w", pady=5, padx=(0, 14))
        self.kit.entry(grid, textvariable=ctk.StringVar(value="200"), mono=True, field="win").grid(
            row=0, column=1, sticky="ew", pady=5)
        self.kit.label(grid, "Modalità coda segnali", color="text2",
                       font=self.kit.f_small).grid(row=1, column=0, sticky="w", pady=5, padx=(0, 14))
        self.queue_var = ctk.StringVar(value=self.queue_mode)
        self.kit.option(
            grid,
            ["OVERWRITE_LAST — tieni solo l'ultimo segnale",
             "APPEND_ACTIVE — accoda i segnali attivi",
             "QUEUE_UNTIL_CONFIRMED — attendi conferma XTrader"],
            variable=self.queue_var, command=self.on_queue_change, field="win", width=420).grid(
            row=1, column=1, sticky="ew", pady=5)

        self.kit.check(f, text="  Avvio automatico all'apertura  (in modalità REALE chiede conferma)"
                       ).grid(row=2, column=0, sticky="w", pady=(11, 0))
        self.kit.check(f, text="  Logga il testo completo dei messaggi  (debug; OFF = solo hash + 1ª riga)"
                       ).grid(row=3, column=0, sticky="w", pady=(6, 0))
        g2 = ctk.CTkFrame(f, fg_color="transparent")
        g2.grid(row=4, column=0, sticky="ew", pady=(11, 0))
        g2.grid_columnconfigure(1, weight=1)
        self.kit.label(g2, "Max segnali attivi  (coda multi-riga)", color="text2",
                       font=self.kit.f_small).grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.kit.entry(g2, textvariable=ctk.StringVar(value=str(self.max_active)), mono=True,
                       field="win").grid(row=0, column=1, sticky="ew")
        return f

    def _cfg_conferme(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(1, weight=1)
        rows = [
            ("Chat notifiche XTrader", "es. -1001234567890", True),
            ("Timeout conferma (sec)", "120", False),
            ("Parole conferma  (sep. virgola)", "confermato, ok, eseguito, piazzato", False),
            ("Parole rifiuto  (sep. virgola)", "rifiutato, annullato, errore, no", False),
        ]
        for i, (label, ph, mono) in enumerate(rows):
            self.kit.label(f, label, color="text2", font=self.kit.f_small).grid(
                row=i, column=0, sticky="w", padx=(0, 14), pady=6)
            default = "120" if label.startswith("Timeout") else ""
            e = self.kit.entry(f, textvariable=ctk.StringVar(value=default),
                               placeholder=ph, mono=mono, field="win")
            e.grid(row=i, column=1, sticky="ew", pady=6)
        return f

    def _set_cfg_tab(self, tid):
        self.cfg_tab = tid
        for k, fr in self.cfg_frames.items():
            fr.pack_forget()
        self.cfg_frames[tid].pack(fill="x")
        self.cfg_tabs.select(tid)

    # ── action bar ───────────────────────────────────────────────────────
    def _build_action_bar(self):
        wrap = ctk.CTkFrame(self.body, fg_color="transparent")
        wrap.pack(fill="x", padx=15, pady=(12, 0))
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x")
        for i in range(4):
            row.grid_columnconfigure(i, weight=1)
        self.btn_start = self.kit.button(row, "▶  AVVIA", kind="success", command=self.start, height=36)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn_stop = self.kit.button(row, "■  STOP", kind="danger", command=self.stop, height=36)
        self.btn_stop.grid(row=0, column=1, sticky="ew", padx=5)
        self.kit.button(row, "Svuota CSV ora", kind="accent", command=self.clear_csv,
                        height=36).grid(row=0, column=2, sticky="ew", padx=5)
        self.kit.button(row, "Salva Config", kind="surface", command=self.save_cfg,
                        height=36).grid(row=0, column=3, sticky="ew", padx=(5, 0))
        self.kit.button(wrap, "Strumenti", kind="purple", command=self.open_tools,
                        height=36).pack(fill="x", pady=(9, 0))

    # ── monitor card ─────────────────────────────────────────────────────
    def _build_monitor_card(self):
        card = self.kit.frame(self.body, fg="surface", border="border", bw=1)
        card.pack(fill="both", expand=True, padx=15, pady=(12, 15))
        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.pack(pady=(10, 0))
        self.mon_tabs = TabBar(bar, self.kit,
                               [("chats", "Chat ascoltate"), ("stato", "Stato"),
                                ("dash", "Dashboard"), ("log", "Log")],
                               "chats", self._set_mon_tab)
        self.mon_tabs.pack()
        holder = ctk.CTkFrame(card, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=15, pady=14)
        self.mon_holder = holder
        self.mon_frames = {
            "chats": self._mon_chats(holder),
            "stato": self._mon_stato(holder),
            "dash": self._mon_dash(holder),
            "log": self._mon_log(holder),
        }
        self._set_mon_tab("chats")

    def _mon_chats(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        self.mon_chats_holder = f
        return f

    def _render_mon_chats(self):
        f = self.mon_chats_holder
        for w in f.winfo_children():
            w.destroy()
        if not self.chats:
            self.kit.label(f, "Nessuna chat configurata. Aggiungine una da  "
                           "Strumenti › Chat sorgenti.", color="text3",
                           font=self.kit.f_small).pack(pady=28)
            return
        for ch in self.chats:
            row = self.kit.frame(f, fg="win", border="border", bw=1, corner=9)
            row.pack(fill="x", pady=3)
            self.kit.label(row, "◉", color="accent", font=self.kit.f_small).pack(side="left", padx=(12, 8), pady=9)
            self.kit.label(row, ch["name"], color="text", font=self.kit.f_small_b).pack(side="left")
            self.kit.label(row, ch["id"], color="text3", font=self.kit.f_mono_s).pack(side="left", padx=10)
            chip = self.kit.frame(row, fg="success_weak", corner=20)
            chip.pack(side="right", padx=12)
            self.kit.label(chip, "attiva", color="success", font=self.kit.f_tiny_b).pack(padx=9, pady=2)

    def _mon_stato(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 12))
        for label in ("Esporta audit reale", "Apri cartella log", "Copia diagnostica"):
            self.kit.button(btns, label, kind="ghost", height=28, font=self.kit.f_tiny_b,
                            command=lambda: self.toast("Fatto")).pack(side="right", padx=(8, 0))
        self.mon_stato_vals = {}
        for label in ("Ultimo segnale", "Ultimo messaggio", "Ultimo CSV", "Ultimo errore"):
            row = self.kit.frame(f, fg="win", border="border2", bw=1, corner=8)
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(1, weight=1)
            self.kit.label(row, label, color="text3", font=self.kit.f_tiny_b, width=130,
                           anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=9)
            v = self.kit.label(row, "—", color="text2", font=self.kit.f_mono_s, anchor="w",
                               justify="left")
            v.grid(row=0, column=1, sticky="w", pady=9, padx=(0, 12))
            self.mon_stato_vals[label] = v
        return f

    def _mon_dash(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        self.kit.label(f, "Contatori di sessione — dall'ultimo AVVIO", color="text3",
                       font=self.kit.f_tiny).pack(anchor="w", pady=(0, 12))
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x")
        self.mon_counter_vals = {}
        cols = 4
        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1, uniform="cc")
        for i, (key, label, color) in enumerate(COUNTER_META):
            card = self.kit.frame(grid, fg="win", border="border", bw=1, corner=11)
            card.grid(row=i // cols, column=i % cols, sticky="ew", padx=5, pady=5)
            strip = self.kit.frame(card, fg=color, corner=0, width=3)
            strip.pack(side="left", fill="y")
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)
            self.kit.label(inner, label.upper(), color="text3", font=self.kit.f_micro_b,
                           anchor="w").pack(anchor="w")
            val = self.kit.label(inner, "0", color=color, font=self.kit.f_counter, anchor="w")
            val.pack(anchor="w")
            self.mon_counter_vals[key] = val
        return f

    def _mon_log(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", pady=(0, 11))
        self.kit.label(top, "Mostra", color="text3", font=self.kit.f_tiny).pack(side="left")
        self.kit.option(top, ["Tutti", "INFO", "WARN", "ERRORE"], field="win",
                        width=110, height=28).pack(side="left", padx=6)
        self.kit.label(top, "Conserva", color="text3", font=self.kit.f_tiny).pack(side="left", padx=(6, 0))
        self.kit.option(top, ["15 giorni", "5 giorni", "30 giorni", "Mai"], field="win",
                        width=110, height=28).pack(side="left", padx=6)
        self.kit.check(top, text=" Debug").pack(side="left", padx=4)
        self.kit.button(top, "Svuota log", kind="ghost", height=28, font=self.kit.f_tiny_b,
                        command=self._clear_logs).pack(side="right")

        box = self.kit.textbox(f, height=210)
        box.pack(fill="both", expand=True)
        self.log_text = box
        self._log_tags_done = False
        return f

    def _log_tags(self):
        t = self.log_text._textbox
        for level, col in (("OK", "success"), ("INFO", "info"), ("WARN", "warn"),
                           ("ERRORE", "danger"), ("time", "text3"), ("msg", "text2")):
            t.tag_configure(level, foreground=self.c(col))
        self._log_tags_done = True

    def _render_logs(self):
        if not hasattr(self, "log_text"):
            return
        t = self.log_text._textbox
        self._log_tags()
        t.configure(state="normal")
        t.delete("1.0", "end")
        if not self.logs:
            t.insert("end", "Nessun evento. Premi AVVIA per iniziare ad ascoltare.\n", ("msg",))
        for e in self.logs:
            t.insert("end", e["time"] + "  ", ("time",))
            lvl = e["level"]
            tag = lvl if lvl in ("OK", "INFO", "WARN", "ERRORE") else "msg"
            t.insert("end", f"{lvl:<6}", (tag,))
            t.insert("end", "  " + e["msg"] + "\n", ("msg",))
        t.configure(state="disabled")

    def _clear_logs(self):
        self.logs = []
        self._render_logs()

    def _set_mon_tab(self, tid):
        self.mon_tab = tid
        for fr in self.mon_frames.values():
            fr.pack_forget()
        self.mon_frames[tid].pack(fill="both", expand=True)
        self.mon_tabs.select(tid)
        if tid == "chats":
            self._render_mon_chats()

    # ══════════════════════════════════════════════════════════════════════
    #  DYNAMIC REFRESH
    # ══════════════════════════════════════════════════════════════════════
    def _refresh_all(self):
        self._refresh_hero()
        self._refresh_banners()
        self._refresh_actions()
        self._refresh_safety()
        self._render_mon_chats()
        self._refresh_stato()
        self._refresh_counters()
        self._render_logs()

    def _refresh_hero(self):
        self.active_lbl.configure(text=f"Righe attive: {self.active_rows}/{self.max_active}")
        st = STATUS[self.status]
        self.pill.configure(fg_color=self.c(st["bg"]))
        self.pill_lbl.configure(text=st["label"], text_color=self.c(st["c"]))
        self.pill_dot.set(st["c"], st["bg"])
        # pulse animation
        if self._pulse_job:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        if st["pulse"]:
            self._pulse(st["pulse"], True)

    def _pulse(self, period, on):
        try:
            st = STATUS[self.status]
        except KeyError:
            return
        col = self.c(st["c"]) if on else self.c(st["bg"])
        try:
            self.pill_dot.itemconfigure(self.pill_dot._oval, fill=col)
        except Exception:
            return
        self._pulse_job = self.after(period // 2, lambda: self._pulse(period, not on))

    def _refresh_banners(self):
        self.real_banner.pack_forget()
        self.warn_banner.pack_forget()
        if self.mode == "real":
            self.real_banner.pack(fill="x", padx=15, pady=(9, 0),
                                  after=self._hero_after())
        if not self.chats:
            self.warn_banner.pack(fill="x", padx=15, pady=(12, 0))

    def _hero_after(self):
        return self.body.winfo_children()[0]  # hero is first child

    def _refresh_actions(self):
        running = self.status != "offline"
        if running:
            self.btn_start.configure(fg_color=self.c("surface2"), text_color=self.c("text3"),
                                     hover_color=self.c("surface2"))
            self.btn_stop.configure(fg_color=self.c("danger"), text_color="#ffffff",
                                    hover_color=self.c("danger_h"))
        else:
            self.btn_start.configure(fg_color=self.c("success"), text_color="#ffffff",
                                     hover_color=self.c("success_h"))
            self.btn_stop.configure(fg_color=self.c("surface2"), text_color=self.c("text3"),
                                    hover_color=self.c("surface2"))

    def _refresh_safety(self):
        if not hasattr(self, "dry_frame"):
            return
        real = self.mode == "real"
        self.dry_frame.configure(fg_color=self.c("danger_weak") if real else self.c("warn_weak"),
                                 border_color=self.c("danger") if real else self.c("warn"))

    def _refresh_stato(self):
        if not hasattr(self, "mon_stato_vals"):
            return
        vals = {"Ultimo segnale": (self.last_signal, "text"),
                "Ultimo messaggio": (self.last_message, "text2"),
                "Ultimo CSV": (self.last_csv, "success"),
                "Ultimo errore": (self.last_error, "text3")}
        for label, (v, col) in vals.items():
            self.mon_stato_vals[label].configure(text=v, text_color=self.c(col))

    def _refresh_counters(self):
        if not hasattr(self, "mon_counter_vals"):
            return
        for key, lbl in self.mon_counter_vals.items():
            lbl.configure(text=str(self.counters[key]))

    # ══════════════════════════════════════════════════════════════════════
    #  BEHAVIOUR / STATE MACHINE
    # ══════════════════════════════════════════════════════════════════════
    def toggle_theme(self):
        self.kit.retheme()
        # dynamic bits not in the registry:
        self._refresh_all()

    def start(self):
        if self.status != "offline":
            return
        if not self.chats:
            self.toast("Configura prima una Chat sorgente")
            self.log("WARN", "AVVIO bloccato: nessuna chat configurata", "warn")
            return
        self.status = "active"
        self.counters = {k: 0 for k, _, _ in COUNTER_META}
        self.active_rows = 0
        self.log("OK", "Listener avviato — connesso a Telegram, in ascolto", "success")
        self._refresh_hero()
        self._refresh_actions()
        self._refresh_counters()
        self._schedule_tick()

    def _schedule_tick(self):
        if self._tick:
            self.after_cancel(self._tick)
        self._tick = self.after(1600, self._sim_event)

    def stop(self):
        if self.status == "offline":
            return
        for job in ("_tick", "_recon"):
            j = getattr(self, job)
            if j:
                self.after_cancel(j)
                setattr(self, job, None)
        self.status = "offline"
        self.log("INFO", "Listener fermato", "text2")
        self._refresh_hero()
        self._refresh_actions()

    def _sim_event(self):
        if self.status == "reconnect":
            return
        if random.random() < 0.07:
            self.status = "reconnect"
            self.log("WARN", "Connessione persa: riconnessione in corso…", "warn")
            self._refresh_hero()
            if self._recon:
                self.after_cancel(self._recon)
            self._recon = self.after(2600, self._reconnect)
            self._schedule_tick()
            return
        teams = random.choice([("Inter", "Milan"), ("Roma", "Lazio"),
                               ("Napoli", "Juve"), ("Atalanta", "Torino")])
        mkt = random.choice(["OVER 2.5", "MATCH ODDS", "GG", "NEXT GOAL"])

        def bump(k):
            self.counters[k] += 1
        bump("received")
        self.last_message = f"{teams[0]} v {teams[1]} · {mkt} @ {1.4 + random.random():.2f}"
        r = random.random()
        if self.mode == "sim":
            bump("dry_run")
            self.last_signal = f"{teams[0]} v {teams[1]} — {mkt}"
            self.log("INFO", f"Segnale {teams[0]}–{teams[1]} riconosciuto (DRY_RUN)", "info")
        elif r < 0.68:
            bump("written")
            self.active_rows = min(self.max_active, self.active_rows + 1)
            self.last_signal = f"{teams[0]} v {teams[1]} — {mkt}"
            self.last_csv = f"segnali.csv @ {self._now()}"
            self.log("OK", f"Riga scritta: {teams[0]} v {teams[1]} — {mkt}", "success")
        elif r < 0.80:
            bump("duplicate")
            self.log("WARN", f"Duplicato ignorato: {teams[0]} v {teams[1]}", "warn")
        elif r < 0.92:
            bump("discarded")
            self.log("WARN", "Scartato: selezione non riconosciuta", "warn")
        else:
            bump("limited")
            self.log("WARN", "Limite raggiunto — segnale in coda", "warn")
        self._refresh_hero()
        self._refresh_counters()
        self._refresh_stato()
        self._schedule_tick()

    def _reconnect(self):
        if self.status == "reconnect":
            self.status = "active"
            self.log("OK", "Riconnesso a Telegram.", "success")
            self._refresh_hero()

    def clear_csv(self):
        self.active_rows = 0
        self.last_csv = f"segnali.csv (svuotato) @ {self._now()}"
        self.log("INFO", "CSV svuotato (solo intestazione)", "text2")
        self.toast("CSV svuotato")
        self._refresh_hero()
        self._refresh_stato()

    def save_cfg(self):
        self.toast("Configurazione salvata")
        self.log("INFO", "Configurazione salvata su config.json", "text2")

    # ── DRY / REAL ───────────────────────────────────────────────────────
    def toggle_dry(self):
        if self.sim_var.get():
            self.mode = "sim"
            self.log("INFO", "Modalità SIMULAZIONE (DRY_RUN) attivata", "info")
            self._after_mode_change()
        else:
            from .dialogs import RealConfirm
            RealConfirm(self, on_confirm=self._enable_real, on_cancel=self._cancel_real)

    def _enable_real(self):
        self.mode = "real"
        self.log("WARN", "REAL_MODE_ENABLED — modalità REALE attivata", "danger")
        self.toast("Modalità REALE attiva")
        self._after_mode_change()

    def _cancel_real(self):
        self.sim_var.set(True)
        self.log("INFO", "Attivazione REALE annullata: resta in simulazione", "text2")

    def _after_mode_change(self):
        self._refresh_safety()
        self._refresh_banners()

    # ── queue / multi-signal ─────────────────────────────────────────────
    def on_queue_change(self, value):
        code = value.split(" ")[0]
        if code in ("APPEND_ACTIVE", "QUEUE_UNTIL_CONFIRMED"):
            # snap back visually until confirmed
            self.queue_var.set(self._queue_label(self.queue_mode))
            from .dialogs import MultiConfirm
            MultiConfirm(self, code, on_confirm=lambda: self._apply_queue(code))
        else:
            self.queue_mode = code

    def _apply_queue(self, code):
        self.queue_mode = code
        self.queue_var.set(self._queue_label(code))
        self.log("WARN", "Modalità MULTI-segnale attivata", "warn")

    @staticmethod
    def _queue_label(code):
        return {
            "OVERWRITE_LAST": "OVERWRITE_LAST — tieni solo l'ultimo segnale",
            "APPEND_ACTIVE": "APPEND_ACTIVE — accoda i segnali attivi",
            "QUEUE_UNTIL_CONFIRMED": "QUEUE_UNTIL_CONFIRMED — attendi conferma XTrader",
        }[code]

    # ── data mutations shared with Tools ─────────────────────────────────
    def on_chats_changed(self):
        self._render_mon_chats()
        self._refresh_banners()

    # ── tools ────────────────────────────────────────────────────────────
    def open_tools(self):
        from .tools import ToolsWindow
        if self.tools_win is not None and self.tools_win.winfo_exists():
            self.tools_win.focus()
            return
        self.tools_win = ToolsWindow(self)

    def _on_close(self):
        for job in ("_tick", "_recon", "_pulse_job", "_toast_job"):
            j = getattr(self, job, None)
            if j:
                try:
                    self.after_cancel(j)
                except Exception:
                    pass
        self.destroy()
