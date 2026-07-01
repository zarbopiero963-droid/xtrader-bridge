"""Tools ('Strumenti') window: Parser builder + 6 supporting tabs."""

from __future__ import annotations

import customtkinter as ctk

from .ui import TabBar
from .parser_engine import (
    CSV_COLS, TRANSFORMS, VALUEMAPS, CATALOG, DEFAULT_MSG,
    default_rules, run_test,
)

CATALOG_LABELS = list(CATALOG.keys())
MARKET_CODES = ["MATCH_ODDS", "OVER_UNDER_25", "BOTH_TEAMS_TO_SCORE", "NEXT_GOAL"]


def _lbl(v):
    return "—" if v == "" else v


def _unlbl(v):
    return "" if v == "—" else v


class ToolsWindow(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.kit, self.c = app, app.kit, app.c
        self.title("Strumenti — XTrader Signal Bridge")
        self.configure(fg_color=self.c("win"))
        self.geometry("1140x790")
        self.minsize(900, 600)
        self.transient(app)

        # ── parser state ─────────────────────────────────────────────────
        self.rules = default_rules()
        self.rule_vars = []
        self.multi_market = False
        self.market_rows = []
        self.multi_selection = False
        self.selection_rows = []
        self.parsers = {}
        self.parser_msg = DEFAULT_MSG
        self._suspend = False
        self.tool_tab = "parser"
        self.map_tab = "teams"

        self._build_titlebar()
        self._build_tabbar()

        self.content = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color=self.c("win"))
        self.kit.add_dynamic(lambda: self.content.configure(fg_color=self.c("win")))
        self.content.pack(fill="both", expand=True)

        self.tab_frames = {
            "parser": self._tab_parser(),
            "src": self._tab_sources(),
            "prov": self._tab_providers(),
            "prof": self._tab_profiles(),
            "map": self._tab_mapping(),
            "sync": self._tab_sync(),
            "diz": self._tab_dictionary(),
        }
        self._show_tab("parser")
        self._run_test()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        self.app.tools_win = None
        self.destroy()

    # ── chrome ───────────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = self.kit.frame(self, fg="titlebar", corner=0, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.kit.label(bar, "⚒  Strumenti", color="purple", font=self.kit.f_small_b).pack(
            side="left", padx=13)
        self.kit.button(bar, "✕", kind="titlebar", width=30, height=28, command=self._close,
                        font=self.kit.f_small_b).pack(side="right", padx=6)

    def _build_tabbar(self):
        wrap = self.kit.frame(self, fg="win", corner=0)
        wrap.pack(fill="x")
        holder = ctk.CTkFrame(wrap, fg_color="transparent")
        holder.pack(pady=12)
        self.tabbar = TabBar(
            holder, self.kit,
            [("parser", "Parser"), ("src", "Chat sorgenti"), ("prov", "Provider"),
             ("prof", "Profili"), ("map", "Mapping"), ("sync", "Betfair Sync"),
             ("diz", "Dizionario Betfair")],
            "parser", self._show_tab, font=self.kit.f_small_b)
        self.tabbar.pack()

    def _show_tab(self, tid):
        self.tool_tab = tid
        for fr in self.tab_frames.values():
            fr.pack_forget()
        self.tab_frames[tid].pack(fill="both", expand=True)
        self.tabbar.select(tid)

    # ══════════════════════════════════════════════════════════════════════
    #  PARSER TAB
    # ══════════════════════════════════════════════════════════════════════
    def _tab_parser(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent")
        wrap.pack(padx=20, pady=18, fill="x")

        # meta row
        meta = ctk.CTkFrame(wrap, fg_color="transparent")
        meta.pack(fill="x", pady=(0, 12))
        self.kit.label(meta, "Nome parser:", color="text2", font=self.kit.f_small).pack(side="left")
        self.p_name = ctk.StringVar()
        self.kit.entry(meta, textvariable=self.p_name, placeholder="es. VIP_Over_Live",
                       field="surface", width=200).pack(side="left", padx=(8, 14))
        self.kit.label(meta, "Modalità:", color="text2", font=self.kit.f_small).pack(side="left")
        self.p_mode = ctk.StringVar(value="NAME_ONLY")
        self.kit.option(meta, ["NAME_ONLY", "ID_ONLY", "BOTH"], variable=self.p_mode,
                        field="surface", width=130).pack(side="left", padx=(8, 14))
        self.kit.label(meta, "Sport:", color="text2", font=self.kit.f_small).pack(side="left")
        self.p_sport = ctk.StringVar(value="(non specificato)")
        self.kit.option(meta, ["(non specificato)", "Calcio", "Tennis", "Basket", "Rugby Union"],
                        variable=self.p_sport, field="surface", width=150).pack(side="left", padx=(8, 14))
        self.kit.button(meta, "＋ Provider", kind="accent", width=110, height=32,
                        font=self.kit.f_small, command=lambda: self._show_tab("prov")).pack(side="left")

        # saved parsers row
        saved = ctk.CTkFrame(wrap, fg_color="transparent")
        saved.pack(fill="x", pady=(0, 14))
        self.kit.label(saved, "Parser salvati:", color="text2", font=self.kit.f_small).pack(side="left")
        self.p_selected = ctk.StringVar(value="(nessuno)")
        self.saved_menu = self.kit.option(saved, ["(nessuno)"], variable=self.p_selected,
                                          field="surface", width=200)
        self.saved_menu.pack(side="left", padx=8)
        for label, kind, cmd in (
            ("＋ Nuovo", "accent", self.p_new), ("⌂ Carica", "accent", self.p_load),
            ("⧉ Duplica", "accent", self.p_dup), ("🗑 Elimina", "danger", self.p_del),
            ("💾 Salva", "success", self.p_save)):
            self.kit.button(saved, label, kind=kind, width=96, height=32, font=self.kit.f_small,
                            command=cmd).pack(side="left", padx=(0, 6))

        # catalog row
        cat = ctk.CTkFrame(wrap, fg_color="transparent")
        cat.pack(fill="x", pady=(0, 14))
        self.kit.label(cat, "Catalogo XTrader:", color="text2", font=self.kit.f_small).pack(side="left")
        self.catalog_market = ctk.StringVar(value="Under/Over 2.5")
        self.kit.option(cat, CATALOG_LABELS, variable=self.catalog_market, field="surface",
                        width=230).pack(side="left", padx=8)
        self.kit.button(cat, "＋ Inserisci regole fisse", kind="accent", width=200, height=32,
                        font=self.kit.f_small, command=self.insert_fixed).pack(side="left")

        # 14-row CSV grid
        self._build_rules_grid(wrap)

        # name / market mapping cards
        self._build_mapping_cards(wrap)

        # multi-row output
        self._build_multirow(wrap)

        # live test
        self._build_test(wrap)
        return root

    def _build_rules_grid(self, parent):
        cols = ["Colonna", "Inizia dopo", "Finisce prima", "Valore fisso",
                "Trasformazione", "Value-map", "Obbl."]
        weights = [0, 1, 1, 0, 0, 0, 0]
        widths = [120, 0, 0, 110, 128, 128, 56]
        grid = self.kit.frame(parent, fg="surface", border="border", bw=1, corner=10)
        grid.pack(fill="x", pady=(0, 14))
        for i, w in enumerate(weights):
            grid.grid_columnconfigure(i, weight=w, minsize=widths[i] or 60)
        for i, col in enumerate(cols):
            head = self.kit.frame(grid, fg="titlebar", corner=0)
            head.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(head, col, color="text3", font=self.kit.f_micro_b,
                           anchor="center" if col == "Obbl." else "w").pack(
                fill="x", padx=9, pady=8)

        self.rule_vars = []
        for r, rule in enumerate(self.rules, start=1):
            req = rule.get("req", False)
            self.kit.label(grid, rule["col"], color="text" if req else "text2",
                           font=self.kit.f_mono_b if req else self.kit.f_mono_s,
                           fg_color="win", corner_radius=0, anchor="w").grid(
                row=r, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            sa = ctk.StringVar(value=rule.get("sa", ""))
            eb = ctk.StringVar(value=rule.get("eb", ""))
            fx = ctk.StringVar(value=rule.get("fx", ""))
            tr = ctk.StringVar(value=_lbl(rule.get("tr", "")))
            vm = ctk.StringVar(value=_lbl(rule.get("vm", "")))
            rq = ctk.BooleanVar(value=req)
            self.rule_vars.append({"sa": sa, "eb": eb, "fx": fx, "tr": tr, "vm": vm, "req": rq})
            idx = r - 1
            for var, field, col, info in ((sa, "sa", 1, False), (eb, "eb", 2, False),
                                          (fx, "fx", 3, True)):
                e = self.kit.entry(grid, textvariable=var, placeholder="—", mono=True,
                                   field="win", height=34)
                if info:
                    e.configure(text_color=self.c("info"))
                    self.kit.themed.append((e, {"text_color": "info", "fg_color": "win",
                                                "border_color": "border"}))
                e.configure(border_width=0)
                e.grid(row=r, column=col, sticky="nsew", padx=(0, 1), pady=(0, 1))
                var.trace_add("write", lambda *_a, i=idx, f=field, v=var: self._on_rule(i, f, v.get()))
            tr_menu = self.kit.option(grid, [_lbl(x) for x in TRANSFORMS], variable=tr,
                                      field="win", width=124, height=34, font=self.kit.f_tiny,
                                      command=lambda val, i=idx: self._on_rule(i, "tr", _unlbl(val)))
            tr_menu.grid(row=r, column=4, sticky="nsew", padx=(0, 1), pady=(0, 1))
            vm_menu = self.kit.option(grid, [_lbl(x) for x in VALUEMAPS], variable=vm,
                                      field="win", width=124, height=34, font=self.kit.f_tiny,
                                      command=lambda val, i=idx: self._on_rule(i, "vm", _unlbl(val)))
            vm_menu.grid(row=r, column=5, sticky="nsew", padx=(0, 1), pady=(0, 1))
            cell = self.kit.frame(grid, fg="win", corner=0)
            cell.grid(row=r, column=6, sticky="nsew", padx=(0, 1), pady=(0, 1))
            chk = ctk.CTkCheckBox(cell, text="", variable=rq, width=20, checkbox_width=15,
                                  checkbox_height=15, corner_radius=4,
                                  command=lambda i=idx, v=rq: self._on_rule(i, "req", v.get()))
            self.kit.reg(chk, fg_color="accent", hover_color="accent", border_color="border",
                         checkmark_color="#ffffff")
            chk.pack(expand=True)

    def _on_rule(self, i, field, value):
        self.rules[i][field] = value
        if not self._suspend:
            self.after_idle(self._run_test)

    def _build_mapping_cards(self, parent):
        names = self.kit.frame(parent, fg="surface", border="border", bw=1, corner=10)
        names.pack(fill="x", pady=(0, 12))
        r1 = ctk.CTkFrame(names, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=12)
        self.kit.label(r1, "Mappatura nomi · separatore:", color="text2",
                       font=self.kit.f_small).pack(side="left")
        self.kit.entry(r1, textvariable=ctk.StringVar(value="v"), mono=True, field="win",
                       width=56).pack(side="left", padx=8)
        self.kit.button(r1, "📖 Dizionario nomi", kind="accent", width=160, height=32,
                        font=self.kit.f_small,
                        command=lambda: self._open_dict("names")).pack(side="left", padx=(0, 14))
        self.kit.label(r1, "Profili:", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.check(r1, text=" test", color="text").pack(side="left", padx=8)

        mkts = self.kit.frame(parent, fg="surface", border="border", bw=1, corner=10)
        mkts.pack(fill="x", pady=(0, 16))
        r2 = ctk.CTkFrame(mkts, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=12)
        self.kit.label(r2, "Mappatura mercati:", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.button(r2, "◎ Dizionario mercati", kind="accent", width=170, height=32,
                        font=self.kit.f_small,
                        command=lambda: self._open_dict("markets")).pack(side="left", padx=(8, 14))
        self.kit.label(r2, "Profili:", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.label(r2, "(nessun profilo)", color="text3", font=self.kit.f_small).pack(side="left", padx=8)

    def _open_dict(self, kind):
        from .dialogs import DictWindow
        DictWindow(self.app, kind)

    def _build_multirow(self, parent):
        box = self.kit.frame(parent, fg="surface", border="border", bw=1, corner=10)
        box.pack(fill="x", pady=(0, 0))
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        self.kit.label(inner, "Output multi-riga  (un messaggio → più righe CSV)",
                       color="text", font=self.kit.f_small_b).pack(anchor="w", pady=(0, 10))

        # MultiMarket
        mrow = ctk.CTkFrame(inner, fg_color="transparent")
        mrow.pack(fill="x", pady=(0, 8))
        self.mm_var = ctk.BooleanVar(value=False)
        self.kit.check(mrow, text="  ▤ MultiMarket (più mercati)", variable=self.mm_var,
                       command=self._toggle_mm, color="text").pack(side="left")
        self.mm_add = self.kit.button(mrow, "＋ Aggiungi mercato", kind="accent", width=150,
                                      height=30, font=self.kit.f_small, command=self._add_market)
        self.mm_add.pack(side="left", padx=12)
        self.mm_table = ctk.CTkFrame(inner, fg_color="transparent")
        self.mm_table.pack(fill="x")

        # MultiSelection
        srow = ctk.CTkFrame(inner, fg_color="transparent")
        srow.pack(fill="x", pady=(10, 8))
        self.ms_var = ctk.BooleanVar(value=False)
        self.kit.check(srow, text="  ☰ MultiSelection (più selezioni)", variable=self.ms_var,
                       command=self._toggle_ms, color="text").pack(side="left")
        self.ms_add = self.kit.button(srow, "＋ Aggiungi selezione", kind="accent", width=160,
                                      height=30, font=self.kit.f_small, command=self._add_selection)
        self.ms_add.pack(side="left", padx=12)
        self.ms_table = ctk.CTkFrame(inner, fg_color="transparent")
        self.ms_table.pack(fill="x")
        self._update_addbtns()

    def _update_addbtns(self):
        for btn, on in ((self.mm_add, self.multi_market), (self.ms_add, self.multi_selection)):
            btn.configure(state="normal" if on else "disabled")

    def _toggle_mm(self):
        self.multi_market = self.mm_var.get()
        if self.multi_market and not self.market_rows:
            self.market_rows.append({"after": "Mercato: ", "before": "\n", "text": "",
                                     "market": "MATCH_ODDS"})
        self._render_markets()
        self._update_addbtns()
        self._run_test()

    def _add_market(self):
        self.market_rows.append({"after": "", "before": "", "text": "", "market": "MATCH_ODDS"})
        self._render_markets()
        self._run_test()

    def _render_markets(self):
        for w in self.mm_table.winfo_children():
            w.destroy()
        if not self.multi_market:
            return
        cols = ["Inizia dopo", "Finisce prima", "Testo mercato", "Mercato (catalogo)", ""]
        tbl = self.kit.frame(self.mm_table, fg="surface", border="border", bw=1, corner=9)
        tbl.pack(fill="x", pady=(4, 12))
        for i in range(4):
            tbl.grid_columnconfigure(i, weight=1, uniform="mm")
        tbl.grid_columnconfigure(4, minsize=40)
        for i, col in enumerate(cols):
            h = self.kit.frame(tbl, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b, anchor="w").pack(
                fill="x", padx=9, pady=7)
        if not self.market_rows:
            self.kit.label(tbl, "Nessun mercato. Premi «Aggiungi mercato».", color="text3",
                           font=self.kit.f_tiny, fg_color="win").grid(
                row=1, column=0, columnspan=5, sticky="nsew", pady=14)
            return
        for r, m in enumerate(self.market_rows, start=1):
            for field, col, mono in (("after", 0, True), ("before", 1, True), ("text", 2, False)):
                var = ctk.StringVar(value=m[field])
                e = self.kit.entry(tbl, textvariable=var, placeholder="—", mono=mono,
                                   field="win", height=34)
                e.configure(border_width=0)
                e.grid(row=r, column=col, sticky="nsew", padx=(0, 1), pady=(0, 1))
                var.trace_add("write", lambda *_a, mm=m, f=field, v=var: self._edit_row(mm, f, v.get()))
            mv = ctk.StringVar(value=m["market"])
            self.kit.option(tbl, MARKET_CODES, variable=mv, field="win", width=120, height=34,
                            font=self.kit.f_tiny,
                            command=lambda val, mm=m: self._edit_row(mm, "market", val)).grid(
                row=r, column=3, sticky="nsew", padx=(0, 1), pady=(0, 1))
            cell = self.kit.frame(tbl, fg="win", corner=0)
            cell.grid(row=r, column=4, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.button(cell, "🗑", kind="titlebar", width=24, height=24, font=self.kit.f_tiny,
                            command=lambda mm=m: self._remove_market(mm)).pack(expand=True)

    def _remove_market(self, m):
        self.market_rows.remove(m)
        self._render_markets()
        self._run_test()

    def _toggle_ms(self):
        self.multi_selection = self.ms_var.get()
        if self.multi_selection and not self.selection_rows:
            self.selection_rows.append({"after": "Selezione: ", "before": "\n", "sel": ""})
        self._render_selections()
        self._update_addbtns()
        self._run_test()

    def _add_selection(self):
        self.selection_rows.append({"after": "", "before": "", "sel": ""})
        self._render_selections()
        self._run_test()

    def _render_selections(self):
        for w in self.ms_table.winfo_children():
            w.destroy()
        if not self.multi_selection:
            return
        cols = ["Inizia dopo", "Finisce prima", "Selezione (catalogo)", ""]
        tbl = self.kit.frame(self.ms_table, fg="surface", border="border", bw=1, corner=9)
        tbl.pack(fill="x", pady=(4, 4))
        for i in range(3):
            tbl.grid_columnconfigure(i, weight=1, uniform="ms")
        tbl.grid_columnconfigure(3, minsize=40)
        for i, col in enumerate(cols):
            h = self.kit.frame(tbl, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b, anchor="w").pack(
                fill="x", padx=9, pady=7)
        if not self.selection_rows:
            self.kit.label(tbl, "Nessuna selezione. Premi «Aggiungi selezione».", color="text3",
                           font=self.kit.f_tiny, fg_color="win").grid(
                row=1, column=0, columnspan=4, sticky="nsew", pady=14)
            return
        for r, m in enumerate(self.selection_rows, start=1):
            for field, col, mono, ph in (("after", 0, True, "—"), ("before", 1, True, "—"),
                                         ("sel", 2, False, "es. Over 2.5 Goals")):
                var = ctk.StringVar(value=m[field])
                e = self.kit.entry(tbl, textvariable=var, placeholder=ph, mono=mono,
                                   field="win", height=34)
                e.configure(border_width=0)
                e.grid(row=r, column=col, sticky="nsew", padx=(0, 1), pady=(0, 1))
                var.trace_add("write", lambda *_a, mm=m, f=field, v=var: self._edit_row(mm, f, v.get()))
            cell = self.kit.frame(tbl, fg="win", corner=0)
            cell.grid(row=r, column=3, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.button(cell, "🗑", kind="titlebar", width=24, height=24, font=self.kit.f_tiny,
                            command=lambda mm=m: self._remove_selection(mm)).pack(expand=True)

    def _remove_selection(self, m):
        self.selection_rows.remove(m)
        self._render_selections()
        self._run_test()

    def _edit_row(self, row, field, value):
        row[field] = value
        if not self._suspend:
            self.after_idle(self._run_test)

    def _build_test(self, parent):
        box = self.kit.frame(parent, fg="surface", border="border", bw=1, corner=10)
        box.pack(fill="x", pady=(16, 0))
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        self.kit.label(inner, "🧪  Messaggio di prova", color="text", font=self.kit.f_small_b).pack(
            anchor="w", pady=(0, 8))
        self.msg_box = self.kit.textbox(inner, height=110)
        self.msg_box.pack(fill="x")
        self.msg_box.insert("1.0", self.parser_msg)
        self.msg_box.bind("<KeyRelease>", lambda e: self._msg_changed())

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(fill="x", pady=(11, 0))
        self.kit.button(btns, "💾 Salva", kind="accent", width=110, height=34,
                        font=self.kit.f_small, command=self.p_save).pack(side="left")
        self.kit.button(btns, "🧪 Prova messaggio", kind="accent", width=160, height=34,
                        font=self.kit.f_small, command=self._run_test).pack(side="left", padx=9)
        self.kit.button(btns, "⧉ Copia diagnostica", kind="accent", width=170, height=34,
                        font=self.kit.f_small,
                        command=lambda: self.app.toast("Diagnostica copiata")).pack(side="left")

        self.verdict_holder = ctk.CTkFrame(inner, fg_color="transparent")
        self.verdict_holder.pack(fill="x", pady=(11, 0))

        self.gen_caption = self.kit.label(inner, "Anteprima righe generate (1)", color="text3",
                                          font=self.kit.f_tiny_b)
        self.gen_caption.pack(anchor="w", pady=(12, 6))
        self.gen_holder = self.kit.frame(inner, fg="surface", border="border", bw=1, corner=9)
        self.gen_holder.pack(fill="x")

        self.kit.label(inner, "Diagnostica (una riga per colonna)", color="text3",
                       font=self.kit.f_tiny_b).pack(anchor="w", pady=(14, 6))
        self.diag_holder = self.kit.frame(inner, fg="surface", border="border", bw=1, corner=9)
        self.diag_holder.pack(fill="x")

    def _msg_changed(self):
        self.parser_msg = self.msg_box.get("1.0", "end-1c")
        self.after_idle(self._run_test)

    # ── the live test ────────────────────────────────────────────────────
    def _run_test(self):
        gen, diag, verdict = run_test(self.parser_msg, self.rules, self.multi_market,
                                      self.market_rows, self.multi_selection, self.selection_rows)
        # verdict bar
        for w in self.verdict_holder.winfo_children():
            w.destroy()
        bar = self.kit.frame(self.verdict_holder, fg=verdict["bg"], border=verdict["color"],
                             bw=1, corner=9)
        bar.pack(fill="x")
        icon = "✓" if verdict["icon"] == "check" else "⚠"
        self.kit.label(bar, f"  {icon}  {verdict['text']}", color=verdict["color"],
                       font=self.kit.f_small_b, justify="left", wraplength=820).pack(
            anchor="w", padx=12, pady=9)

        # generated rows
        self.gen_caption.configure(text=f"Anteprima righe generate ({len(gen)})")
        for w in self.gen_holder.winfo_children():
            w.destroy()
        self.gen_holder.grid_columnconfigure(0, minsize=34)
        self.gen_holder.grid_columnconfigure(1, minsize=90)
        self.gen_holder.grid_columnconfigure(2, weight=1)
        for i, col in enumerate(("#", "Esito", "Campi valorizzati")):
            h = self.kit.frame(self.gen_holder, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b, anchor="w").pack(
                fill="x", padx=9, pady=6)
        for r, g in enumerate(gen, start=1):
            self.kit.label(self.gen_holder, str(g["idx"]), color="text3", font=self.kit.f_mono_s,
                           fg_color="win", anchor="w").grid(row=r, column=0, sticky="nsew",
                                                            padx=(0, 1), pady=(0, 1))
            self.kit.label(self.gen_holder, g["esito"], color=g["color"], font=self.kit.f_tiny_b,
                           fg_color="win", anchor="w").grid(row=r, column=1, sticky="nsew",
                                                            padx=(0, 1), pady=(0, 1))
            self.kit.label(self.gen_holder, g["summary"], color="text", font=self.kit.f_mono_s,
                           fg_color="win", anchor="w", justify="left", wraplength=560).grid(
                row=r, column=2, sticky="nsew", padx=(0, 1), pady=(0, 1))

        # diagnostics
        for w in self.diag_holder.winfo_children():
            w.destroy()
        self.diag_holder.grid_columnconfigure(0, minsize=120)
        self.diag_holder.grid_columnconfigure(1, minsize=74)
        self.diag_holder.grid_columnconfigure(2, weight=1)
        for i, col in enumerate(("Colonna", "Stato", "Valore estratto")):
            h = self.kit.frame(self.diag_holder, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b, anchor="w").pack(
                fill="x", padx=9, pady=6)
        for r, d in enumerate(diag, start=1):
            self.kit.label(self.diag_holder, d["col"], color="text2", font=self.kit.f_mono_s,
                           fg_color="win", anchor="w").grid(row=r, column=0, sticky="nsew",
                                                            padx=(0, 1), pady=(0, 1))
            self.kit.label(self.diag_holder, d["status"], color=d["color"], font=self.kit.f_tiny_b,
                           fg_color="win", anchor="w").grid(row=r, column=1, sticky="nsew",
                                                            padx=(0, 1), pady=(0, 1))
            self.kit.label(self.diag_holder, d["val"], color="text", font=self.kit.f_mono_s,
                           fg_color="win", anchor="w").grid(row=r, column=2, sticky="nsew",
                                                            padx=(0, 1), pady=(0, 1))

    # ── saved-parser CRUD ────────────────────────────────────────────────
    def _snapshot(self):
        return {"mode": self.p_mode.get(), "sport": self.p_sport.get(),
                "rules": [dict(r) for r in self.rules],
                "multiMarket": self.multi_market, "marketRows": [dict(r) for r in self.market_rows],
                "multiSelection": self.multi_selection,
                "selectionRows": [dict(r) for r in self.selection_rows]}

    def _refresh_saved_menu(self):
        vals = ["(nessuno)"] + list(self.parsers.keys())
        self.saved_menu.configure(values=vals)

    def _apply_rules_to_vars(self):
        for i, rule in enumerate(self.rules):
            v = self.rule_vars[i]
            v["sa"].set(rule.get("sa", ""))
            v["eb"].set(rule.get("eb", ""))
            v["fx"].set(rule.get("fx", ""))
            v["tr"].set(_lbl(rule.get("tr", "")))
            v["vm"].set(_lbl(rule.get("vm", "")))
            v["req"].set(rule.get("req", False))

    def p_save(self):
        n = self.p_name.get().strip()
        if not n:
            self.app.toast("Dai un nome al parser")
            return
        self.parsers[n] = self._snapshot()
        self.p_selected.set(n)
        self._refresh_saved_menu()
        self.app.log("OK", f"Parser «{n}» salvato", "success")
        self.app.toast(f"Parser «{n}» salvato")

    def p_new(self):
        self._suspend = True
        self.rules = default_rules()
        self._apply_rules_to_vars()
        self.p_name.set("")
        self.p_mode.set("NAME_ONLY")
        self.p_sport.set("(non specificato)")
        self.p_selected.set("(nessuno)")
        self.multi_market = self.multi_selection = False
        self.market_rows = []
        self.selection_rows = []
        self.mm_var.set(False)
        self.ms_var.set(False)
        self._render_markets()
        self._render_selections()
        self._update_addbtns()
        self._suspend = False
        self._run_test()
        self.app.toast("Nuovo parser")

    def p_load(self):
        n = self.p_selected.get()
        if n in ("", "(nessuno)") or n not in self.parsers:
            self.app.toast("Seleziona un parser salvato")
            return
        p = self.parsers[n]
        self._suspend = True
        self.rules = [dict(r) for r in p["rules"]]
        self.p_name.set(n)
        self.p_mode.set(p["mode"])
        self.p_sport.set(p["sport"])
        self.multi_market = p["multiMarket"]
        self.multi_selection = p["multiSelection"]
        self.market_rows = [dict(r) for r in p["marketRows"]]
        self.selection_rows = [dict(r) for r in p["selectionRows"]]
        self.mm_var.set(self.multi_market)
        self.ms_var.set(self.multi_selection)
        self._apply_rules_to_vars()
        self._render_markets()
        self._render_selections()
        self._update_addbtns()
        self._suspend = False
        self._run_test()
        self.app.log("INFO", f"Parser «{n}» caricato", "info")
        self.app.toast(f"Caricato «{n}»")

    def p_dup(self):
        n = self.p_name.get().strip() or self.p_selected.get()
        if n in ("", "(nessuno)"):
            self.app.toast("Niente da duplicare")
            return
        copy = f"{n}_copia"
        self.parsers[copy] = self._snapshot()
        self.p_name.set(copy)
        self.p_selected.set(copy)
        self._refresh_saved_menu()
        self.app.toast(f"Duplicato in «{copy}»")

    def p_del(self):
        n = self.p_selected.get()
        if n in ("", "(nessuno)") or n not in self.parsers:
            self.app.toast("Seleziona un parser")
            return
        del self.parsers[n]
        self.p_selected.set("(nessuno)")
        self._refresh_saved_menu()
        self.app.log("WARN", f"Parser «{n}» eliminato", "warn")
        self.app.toast(f"Eliminato «{n}»")

    def insert_fixed(self):
        c = CATALOG.get(self.catalog_market.get())
        if not c:
            return
        self.rules = [r for r in self.rules if r["col"] not in ("MarketType", "BetType")]
        self.rules.append({"col": "MarketType", "sa": "", "eb": "", "fx": c["market"],
                           "tr": "", "vm": "", "req": True})
        if c["bet"]:
            self.rules.append({"col": "BetType", "sa": "", "eb": "", "fx": c["bet"],
                               "tr": "", "vm": "", "req": False})
        # keep grid order stable: reorder by CSV_COLS
        order = {col: i for i, col in enumerate(CSV_COLS)}
        self.rules.sort(key=lambda r: order.get(r["col"], 99))
        self._suspend = True
        self._apply_rules_to_vars()
        self._suspend = False
        self._run_test()
        self.app.log("INFO", f"Regole fisse inserite da catalogo: {self.catalog_market.get()}", "info")
        self.app.toast("Regole fisse inserite")

    # ══════════════════════════════════════════════════════════════════════
    #  CHAT SORGENTI
    # ══════════════════════════════════════════════════════════════════════
    def _tab_sources(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=20, pady=18)
        self.kit.label(wrap, "◉ Chat sorgenti  (multi-chat)", color="text",
                       font=self.kit.f_h2).pack(anchor="w")
        self.kit.label(wrap, "Ogni sorgente è una chat/canale da cui accettare segnali. chat_id "
                       "obbligatorio e univoco; una sorgente disattivata viene ignorata.",
                       color="text3", font=self.kit.f_tiny, justify="left").pack(anchor="w", pady=(4, 13))
        self.src_table = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        self.src_table.pack(fill="x")
        self._render_sources()
        foot = ctk.CTkFrame(wrap, fg_color="transparent")
        foot.pack(fill="x", pady=13)
        self.kit.button(foot, "＋ Aggiungi sorgente", kind="accent", width=170,
                        font=self.kit.f_small_b, command=self._add_source).pack(side="left")
        self.kit.button(foot, "💾 Salva", kind="success", width=110, font=self.kit.f_small_b,
                        command=lambda: self.app.toast("Salvato")).pack(side="right")
        return root

    def _render_sources(self):
        for w in self.src_table.winfo_children():
            w.destroy()
        cols = ["Attiva", "Nome", "Chat ID", "Modalità", "Provider", "Parser", ""]
        minsizes = [56, 0, 150, 120, 120, 130, 40]
        for i, ms in enumerate(minsizes):
            self.src_table.grid_columnconfigure(i, minsize=ms, weight=1 if i == 1 else 0)
        for i, col in enumerate(cols):
            h = self.kit.frame(self.src_table, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b,
                           anchor="center" if i == 0 else "w").pack(fill="x", padx=10, pady=8)
        if not self.app.chats:
            self.kit.label(self.src_table, "Nessuna sorgente. Premi «Aggiungi sorgente».",
                           color="text3", font=self.kit.f_small, fg_color="surface").grid(
                row=1, column=0, columnspan=7, pady=24)
            return
        for r, ch in enumerate(self.app.chats, start=1):
            cell = self.kit.frame(self.src_table, fg="surface", corner=0)
            cell.grid(row=r, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            chk = ctk.CTkCheckBox(cell, text="", width=20, checkbox_width=15, checkbox_height=15,
                                  corner_radius=4)
            chk.select()
            self.kit.reg(chk, fg_color="accent", hover_color="accent", border_color="border",
                         checkmark_color="#ffffff")
            chk.pack(expand=True)
            name = ctk.StringVar(value=ch["name"])
            e1 = self.kit.entry(self.src_table, textvariable=name, field="surface", height=36)
            e1.configure(border_width=0)
            e1.grid(row=r, column=1, sticky="nsew", padx=(0, 1), pady=(0, 1))
            name.trace_add("write", lambda *_a, cc=ch, v=name: self._edit_chat(cc, "name", v.get()))
            cid = ctk.StringVar(value=ch["id"])
            e2 = self.kit.entry(self.src_table, textvariable=cid, mono=True, field="surface", height=36)
            e2.configure(border_width=0)
            e2.grid(row=r, column=2, sticky="nsew", padx=(0, 1), pady=(0, 1))
            cid.trace_add("write", lambda *_a, cc=ch, v=cid: self._edit_chat(cc, "id", v.get()))
            self.kit.option(self.src_table, ["NAME_ONLY", "ID_ONLY", "BOTH"], field="surface",
                            width=110, height=36, font=self.kit.f_tiny).grid(
                row=r, column=3, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.option(self.src_table, ["TelegramBot", "test"], field="surface", width=110,
                            height=36, font=self.kit.f_tiny).grid(
                row=r, column=4, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.option(self.src_table, ["(auto)", "VIP_Over"], field="surface", width=120,
                            height=36, font=self.kit.f_tiny).grid(
                row=r, column=5, sticky="nsew", padx=(0, 1), pady=(0, 1))
            cell2 = self.kit.frame(self.src_table, fg="surface", corner=0)
            cell2.grid(row=r, column=6, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.button(cell2, "🗑", kind="titlebar", width=26, height=26, font=self.kit.f_tiny,
                            command=lambda cc=ch: self._remove_source(cc)).pack(expand=True)

    def _edit_chat(self, ch, field, value):
        ch[field] = value
        self.app.on_chats_changed()

    def _add_source(self):
        self.app.chats.append({"name": "Nuova sorgente", "id": ""})
        self._render_sources()
        self.app.on_chats_changed()

    def _remove_source(self, ch):
        self.app.chats.remove(ch)
        self._render_sources()
        self.app.on_chats_changed()

    # ══════════════════════════════════════════════════════════════════════
    #  PROVIDER
    # ══════════════════════════════════════════════════════════════════════
    def _tab_providers(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent", width=800)
        wrap.pack(fill="x", padx=20, pady=18, anchor="w")
        self.kit.label(wrap, "🏷 Anagrafica Provider", color="text", font=self.kit.f_h2).pack(anchor="w")
        self.kit.label(wrap, "Nomi Provider riutilizzabili nel Parser Personalizzato (colonna "
                       "Provider). Valgono per tutti i parser.", color="text3",
                       font=self.kit.f_tiny, justify="left").pack(anchor="w", pady=(4, 14))
        add = ctk.CTkFrame(wrap, fg_color="transparent")
        add.pack(fill="x", pady=(0, 16))
        self.new_provider = ctk.StringVar()
        self.kit.entry(add, textvariable=self.new_provider, placeholder="Nome del nuovo Provider",
                       field="surface", height=36).pack(side="left", fill="x", expand=True)
        self.kit.button(add, "＋ Aggiungi", kind="success", width=120, height=36,
                        font=self.kit.f_small_b, command=self._add_provider).pack(side="left", padx=(10, 0))
        self.prov_list = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        self.prov_list.pack(fill="x")
        self._render_providers()
        return root

    def _render_providers(self):
        for w in self.prov_list.winfo_children():
            w.destroy()
        self.kit.label(self.prov_list, "Provider salvati", color="text2", font=self.kit.f_tiny_b,
                       fg_color="titlebar", corner_radius=0, anchor="w").pack(fill="x", ipady=4, padx=0)
        if not self.app.providers:
            self.kit.label(self.prov_list, "Nessun provider.", color="text3",
                           font=self.kit.f_small).pack(pady=20)
            return
        for p in self.app.providers:
            row = ctk.CTkFrame(self.prov_list, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=6)
            self.kit.label(row, "🏷", color="accent", font=self.kit.f_small).pack(side="left")
            self.kit.label(row, p, color="text", font=self.kit.f_mono_b).pack(side="left", padx=10)
            self.kit.button(row, "🗑 Rimuovi", kind="danger", width=100, height=30,
                            font=self.kit.f_tiny_b,
                            command=lambda pp=p: self._remove_provider(pp)).pack(side="right")

    def _add_provider(self):
        n = self.new_provider.get().strip()
        if not n:
            return
        self.app.providers.append(n)
        self.new_provider.set("")
        self._render_providers()
        self.app.toast("Provider aggiunto")

    def _remove_provider(self, p):
        if p in self.app.providers:
            self.app.providers.remove(p)
        self._render_providers()

    # ══════════════════════════════════════════════════════════════════════
    #  PROFILI
    # ══════════════════════════════════════════════════════════════════════
    def _tab_profiles(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent", width=800)
        wrap.pack(fill="x", padx=20, pady=18, anchor="w")
        self.kit.label(wrap, "⌂ Profili impostazioni", color="text", font=self.kit.f_h2).pack(anchor="w")
        self.kit.label(wrap, "Salva la configurazione corrente come profilo con un nome e "
                       "ricaricala quando vuoi. Il token Telegram NON viene salvato nei profili "
                       "e resta invariato al caricamento.", color="text3", font=self.kit.f_tiny,
                       justify="left", wraplength=740).pack(anchor="w", pady=(4, 14))
        add = ctk.CTkFrame(wrap, fg_color="transparent")
        add.pack(fill="x", pady=(0, 16))
        self.kit.entry(add, textvariable=ctk.StringVar(), placeholder="Nome profilo (es. Prematch)",
                       field="surface", height=36).pack(side="left", fill="x", expand=True)
        self.kit.button(add, "💾 Salva profilo", kind="success", width=150, height=36,
                        font=self.kit.f_small_b, command=lambda: self.app.toast("Salvato")).pack(
            side="left", padx=(10, 0))
        lst = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        lst.pack(fill="x")
        self.kit.label(lst, "Profili salvati", color="text2", font=self.kit.f_tiny_b,
                       fg_color="titlebar", corner_radius=0, anchor="w").pack(fill="x", ipady=4)
        self.kit.label(lst, "(nessun profilo salvato)", color="text3",
                       font=self.kit.f_small).pack(pady=22)
        return root

    # ══════════════════════════════════════════════════════════════════════
    #  MAPPING
    # ══════════════════════════════════════════════════════════════════════
    def _tab_mapping(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=20, pady=(14, 18))
        tb = ctk.CTkFrame(wrap, fg_color="transparent")
        tb.pack(pady=(0, 14))
        self.map_tabs = TabBar(tb, self.kit, [("teams", "Calcio"), ("markets", "Mercati")],
                               "teams", self._set_map_tab)
        self.map_tabs.pack()
        self.map_title = self.kit.label(wrap, "📖 Dizionario nomi squadra", color="text",
                                        font=self.kit.f_h2)
        self.map_title.pack(anchor="w")
        self.map_desc = self.kit.label(wrap, "", color="text3", font=self.kit.f_tiny,
                                       justify="left", wraplength=900)
        self.map_desc.pack(anchor="w", pady=(4, 13))

        prof = ctk.CTkFrame(wrap, fg_color="transparent")
        prof.pack(fill="x", pady=(0, 13))
        self.kit.label(prof, "Profilo:", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.option(prof, ["test"], field="surface", width=190).pack(side="left", padx=8)
        for label, kind in (("＋ Nuovo", "accent"), ("✎ Rinomina", "accent"), ("🗑 Elimina", "danger")):
            self.kit.button(prof, label, kind=kind, width=110, height=32, font=self.kit.f_small,
                            command=lambda: self.app.toast("Fatto")).pack(side="left", padx=(0, 6))

        self.map_table = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        self.map_table.pack(fill="x")
        foot = ctk.CTkFrame(wrap, fg_color="transparent")
        foot.pack(fill="x", pady=13)
        self.kit.button(foot, "＋ Aggiungi riga", kind="accent", width=150, font=self.kit.f_small_b,
                        command=self._add_map_row).pack(side="left")
        self.kit.button(foot, "💾 Salva profilo", kind="success", width=150, font=self.kit.f_small_b,
                        command=lambda: self.app.toast("Salvato")).pack(side="right")
        self._set_map_tab("teams")
        return root

    def _set_map_tab(self, tid):
        self.map_tab = tid
        teams = tid == "teams"
        self.map_title.configure(text="📖 Dizionario nomi squadra" if teams else "📖 Dizionario mercati")
        self.map_desc.configure(text=(
            "Traduce i nomi squadra del canale (Provider) nel nome atteso da Betfair/XTrader. "
            "Seleziona i profili nel Parser Personalizzato." if teams else
            "Traduce le frasi di mercato del canale nel mercato XTrader corrispondente."))
        self.map_tabs.select(tid)
        self._render_map()

    def _render_map(self):
        for w in self.map_table.winfo_children():
            w.destroy()
        if self.map_tab == "teams":
            cols = ["Country (opz.)", "Betfair / XTrader", "Provider", "Sport", "Tipo", ""]
            minsizes = [150, 0, 0, 150, 150, 40]
            weights = [0, 1, 1, 0, 0, 0]
        else:
            cols = ["Frase canale", "Mercato XTrader", "Sport", ""]
            minsizes = [0, 0, 150, 40]
            weights = [1, 1, 0, 0]
        for i, (ms, wt) in enumerate(zip(minsizes, weights)):
            self.map_table.grid_columnconfigure(i, minsize=ms, weight=wt)
        for i, col in enumerate(cols):
            h = self.kit.frame(self.map_table, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b, anchor="w").pack(
                fill="x", padx=10, pady=8)
        rows = self.app.team_map if self.map_tab == "teams" else self.app.market_map
        for r, m in enumerate(rows, start=1):
            if self.map_tab == "teams":
                for field, col, color in (("country", 0, "text"), ("betfair", 1, "text"),
                                          ("provider", 2, "text2")):
                    e = self.kit.entry(self.map_table, textvariable=ctk.StringVar(value=m[field]),
                                       field="surface", height=36)
                    e.configure(border_width=0, text_color=self.c(color))
                    e.grid(row=r, column=col, sticky="nsew", padx=(0, 1), pady=(0, 1))
                self.kit.option(self.map_table, ["(tutti gli sport)", "Calcio", "Tennis"],
                                field="surface", width=140, height=36, font=self.kit.f_tiny).grid(
                    row=r, column=3, sticky="nsew", padx=(0, 1), pady=(0, 1))
                self.kit.option(self.map_table, ["(qualsiasi tipo)", "Squadra", "Giocatore"],
                                field="surface", width=140, height=36, font=self.kit.f_tiny).grid(
                    row=r, column=4, sticky="nsew", padx=(0, 1), pady=(0, 1))
                rmcol = 5
            else:
                e1 = self.kit.entry(self.map_table, textvariable=ctk.StringVar(value=m["from"]),
                                    field="surface", height=36)
                e1.configure(border_width=0)
                e1.grid(row=r, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
                e2 = self.kit.entry(self.map_table, textvariable=ctk.StringVar(value=m["to"]),
                                    field="surface", mono=True, height=36)
                e2.configure(border_width=0, text_color=self.c("info"))
                e2.grid(row=r, column=1, sticky="nsew", padx=(0, 1), pady=(0, 1))
                self.kit.option(self.map_table, ["(tutti gli sport)", "Calcio"], field="surface",
                                width=140, height=36, font=self.kit.f_tiny).grid(
                    row=r, column=2, sticky="nsew", padx=(0, 1), pady=(0, 1))
                rmcol = 3
            cell = self.kit.frame(self.map_table, fg="surface", corner=0)
            cell.grid(row=r, column=rmcol, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.button(cell, "🗑", kind="titlebar", width=26, height=26, font=self.kit.f_tiny,
                            command=lambda mm=m: self._remove_map(mm)).pack(expand=True)

    def _add_map_row(self):
        if self.map_tab == "teams":
            self.app.team_map.append({"country": "", "betfair": "", "provider": ""})
        else:
            self.app.market_map.append({"from": "", "to": ""})
        self._render_map()

    def _remove_map(self, m):
        (self.app.team_map if self.map_tab == "teams" else self.app.market_map).remove(m)
        self._render_map()

    # ══════════════════════════════════════════════════════════════════════
    #  BETFAIR SYNC
    # ══════════════════════════════════════════════════════════════════════
    def _tab_sync(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent", width=720)
        wrap.pack(fill="x", padx=20, pady=18, anchor="w")
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        self.kit.label(head, "⟳ Betfair Sync", color="text", font=self.kit.f_h2).pack(side="left")
        chip = self.kit.frame(head, fg="info_weak", corner=20)
        chip.pack(side="left", padx=10)
        self.kit.label(chip, "locale · read-only", color="info", font=self.kit.f_tiny_b).pack(
            padx=9, pady=2)

        cred = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        cred.pack(fill="x", pady=(0, 12))
        grid = ctk.CTkFrame(cred, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=14)
        grid.grid_columnconfigure(1, weight=1)
        creds = [("Delayed App Key", "chiave delayed", True), ("Username Betfair.it", "username", False),
                 ("Password Betfair.it", "password", True), ("Certificato (.crt/.pem)", "percorso certificato", False),
                 ("Private key (.key)", "percorso chiave", False)]
        for i, (label, ph, secret) in enumerate(creds):
            self.kit.label(grid, label, color="text2", font=self.kit.f_small).grid(
                row=i, column=0, sticky="w", padx=(0, 14), pady=4)
            e = self.kit.entry(grid, textvariable=ctk.StringVar(), placeholder=ph, field="win",
                               mono=("key" in label.lower() or "cert" in label.lower()))
            if secret:
                e.configure(show="•")
            e.grid(row=i, column=1, sticky="ew", pady=4)

        opts = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        opts.pack(fill="x", pady=(0, 12))
        sportrow = ctk.CTkFrame(opts, fg_color="transparent")
        sportrow.pack(fill="x", padx=16, pady=(14, 0))
        self.kit.label(sportrow, "Sport", color="text2", font=self.kit.f_small).pack(side="left")
        for sp in ("Calcio", "Tennis", "Basket", "Rugby Union"):
            cb = self.kit.check(sportrow, text=f" {sp}")
            cb.select()
            cb.pack(side="left", padx=(12, 0))
        drow = ctk.CTkFrame(opts, fg_color="transparent")
        drow.pack(fill="x", padx=16, pady=12)
        self.kit.label(drow, "Giorni avanti", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.entry(drow, textvariable=ctk.StringVar(value="3"), mono=True, field="win",
                       width=56, height=28).pack(side="left", padx=10)

        auto = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        auto.pack(fill="x", pady=(0, 14))
        arow = ctk.CTkFrame(auto, fg_color="transparent")
        arow.pack(fill="x", padx=16, pady=(14, 6))
        self.kit.check(arow, text=" Auto sincronizza dizionario", color="text").pack(side="left")
        self.kit.label(arow, "Orario (HH)", color="text3", font=self.kit.f_tiny).pack(side="left", padx=(12, 6))
        self.kit.entry(arow, textvariable=ctk.StringVar(value="23"), mono=True, field="win",
                       width=52, height=28).pack(side="left")
        for line in ("Ultima auto sync: —", "Prossima auto sync: —", "Stato auto sync: —"):
            self.kit.label(auto, line, color="text2", font=self.kit.f_small).pack(anchor="w", padx=16)
        self.kit.label(auto, "", font=self.kit.f_tiny).pack(pady=2)

        actions = ctk.CTkFrame(wrap, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 12))
        self.kit.button(actions, "🔑 Accedi", kind="accent", width=110, font=self.kit.f_small).pack(side="left", padx=(0, 8))
        self.kit.button(actions, "⟳ Sincronizza ora", kind="accent", width=150, font=self.kit.f_small).pack(side="left", padx=(0, 8))
        self.kit.button(actions, "💾 Salva credenziali", kind="success", width=160, font=self.kit.f_small).pack(side="left", padx=(0, 8))
        self.kit.button(actions, "⤿ Logout", kind="ghost", width=100, font=self.kit.f_small).pack(side="left")
        for line in ("Stato login: — non connesso", "Ultima sync: —", "Stato sync: —"):
            self.kit.label(wrap, line, color="text2", font=self.kit.f_small).pack(anchor="w")
        return root

    # ══════════════════════════════════════════════════════════════════════
    #  DIZIONARIO BETFAIR
    # ══════════════════════════════════════════════════════════════════════
    def _tab_dictionary(self):
        root = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap = ctk.CTkFrame(root, fg_color="transparent")
        wrap.pack(fill="x", padx=20, pady=18)
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        self.kit.label(head, "📖 Dizionario Betfair", color="text", font=self.kit.f_h2).pack(side="left")
        chip = self.kit.frame(head, fg="surface2", corner=20)
        chip.pack(side="left", padx=10)
        self.kit.label(chip, "locale · sola lettura", color="text3", font=self.kit.f_tiny_b).pack(
            padx=9, pady=2)

        f1 = ctk.CTkFrame(wrap, fg_color="transparent")
        f1.pack(fill="x", pady=(0, 10))
        self.kit.label(f1, "Livello", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.option(f1, ["Sport", "Competizioni", "Eventi", "Mercati", "Selezioni"],
                        field="surface", width=150).pack(side="left", padx=(6, 14))
        self.kit.label(f1, "Sport", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.option(f1, ["(tutti gli sport)", "Calcio", "Tennis"], field="surface",
                        width=160).pack(side="left", padx=(6, 14))
        self.kit.check(f1, text=" Solo attivi").pack(side="left")
        self.kit.button(f1, "⟳ Aggiorna", kind="accent", width=110, height=32,
                        font=self.kit.f_small).pack(side="left", padx=12)

        f2 = ctk.CTkFrame(wrap, fg_color="transparent")
        f2.pack(fill="x", pady=(0, 10))
        self.kit.label(f2, "Cerca", color="text2", font=self.kit.f_small).pack(side="left")
        self.kit.entry(f2, textvariable=ctk.StringVar(), placeholder="filtra righe…",
                       field="surface", width=320).pack(side="left", padx=8)
        self.kit.button(f2, "Pulisci", kind="accent", width=90, height=32,
                        font=self.kit.f_small).pack(side="left")
        self.kit.label(wrap, "Sport: 4 totali, 4 attivi (mostrate 4 righe).", color="text3",
                       font=self.kit.f_tiny).pack(anchor="w", pady=(0, 10))

        table = self.kit.frame(wrap, fg="surface", border="border", bw=1, corner=10)
        table.pack(fill="x")
        cols = ["Event Type ID", "Sport", "Ultima sync", "Attivo"]
        minsizes = [130, 0, 160, 80]
        for i, ms in enumerate(minsizes):
            table.grid_columnconfigure(i, minsize=ms, weight=1 if i == 1 else 0)
        for i, col in enumerate(cols):
            h = self.kit.frame(table, fg="titlebar", corner=0)
            h.grid(row=0, column=i, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(h, col, color="text3", font=self.kit.f_micro_b,
                           anchor="center" if i == 3 else "w").pack(fill="x", padx=11, pady=8)
        rows = [("1", "Calcio"), ("2", "Tennis"), ("7522", "Basket"), ("5", "Rugby Union")]
        for r, (rid, sport) in enumerate(rows, start=1):
            self.kit.label(table, rid, color="info", font=self.kit.f_mono_s, fg_color="surface",
                           anchor="w").grid(row=r, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(table, sport, color="text", font=self.kit.f_small, fg_color="surface",
                           anchor="w").grid(row=r, column=1, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.kit.label(table, "oggi 06:00", color="text2", font=self.kit.f_mono_s,
                           fg_color="surface", anchor="w").grid(row=r, column=2, sticky="nsew",
                                                                padx=(0, 1), pady=(0, 1))
            self.kit.label(table, "✓", color="success", font=self.kit.f_small_b,
                           fg_color="surface").grid(row=r, column=3, sticky="nsew",
                                                     padx=(0, 1), pady=(0, 1))
        return root
