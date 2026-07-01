"""Reusable themed widget kit for the XTrader Bridge GUI.

A single :class:`Kit` owns the palette, a registry of themed widgets and a list
of dynamic re-render callbacks, so the whole app (main window + every Toplevel)
re-colours atomically when the light/dark switch is flipped.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

import customtkinter as ctk

from .theme import Palette

# (fg, text, hover, border) — border None means no outline
_BTN_KINDS = {
    "accent":   ("accent", "on_accent", "accent_h", None),
    "success":  ("success", "on_accent", "success_h", None),
    "danger":   ("danger", "on_accent", "danger_h", None),
    "purple":   ("purple", "on_accent", "purple_h", None),
    "warn":     ("warn", "warn_ink", "warn_h", None),
    "surface":  ("surface3", "text", "surface3_h", "border"),
    "ghost":    ("win", "text2", "ghost_h", "border"),
    "titlebar": ("transparent", "text3", "surface2", None),
}


def _pick_family(root, candidates, fallback):
    fams = set(tkfont.families(root))
    for c in candidates:
        if c in fams:
            return c
    return fallback


class Kit:
    def __init__(self, root, mode="dark"):
        self.root = root
        self.pal = Palette(mode)
        self.themed: list[tuple] = []
        self.dynamic: list = []

        sans = _pick_family(root, ["Hanken Grotesk", "Inter", "Segoe UI",
                                   "Helvetica Neue", "DejaVu Sans"], "TkDefaultFont")
        mono = _pick_family(root, ["IBM Plex Mono", "JetBrains Mono", "Consolas",
                                   "DejaVu Sans Mono", "Courier New"], "TkFixedFont")
        self.sans, self.mono = sans, mono
        self.f_base = ctk.CTkFont(sans, 13)
        self.f_bold = ctk.CTkFont(sans, 13, "bold")
        self.f_small = ctk.CTkFont(sans, 12)
        self.f_small_b = ctk.CTkFont(sans, 12, "bold")
        self.f_tiny = ctk.CTkFont(sans, 11)
        self.f_tiny_b = ctk.CTkFont(sans, 11, "bold")
        self.f_micro_b = ctk.CTkFont(sans, 10, "bold")
        self.f_btn = ctk.CTkFont(sans, 13, "bold")
        self.f_h1 = ctk.CTkFont(sans, 17, "bold")
        self.f_h2 = ctk.CTkFont(sans, 15, "bold")
        self.f_pill = ctk.CTkFont(sans, 12, "bold")
        self.f_counter = ctk.CTkFont(mono, 22, "bold")
        self.f_mono = ctk.CTkFont(mono, 12)
        self.f_mono_b = ctk.CTkFont(mono, 12, "bold")
        self.f_mono_s = ctk.CTkFont(mono, 11)

    # ── theming core ──────────────────────────────────────────────────────
    def color(self, key):
        return self.pal(key)

    def reg(self, w, **roles):
        self.themed.append((w, roles))
        self._apply(w, roles)
        return w

    def _apply(self, w, roles):
        try:
            w.configure(**{k: self.pal(v) for k, v in roles.items()})
        except Exception:
            pass

    def add_dynamic(self, cb):
        self.dynamic.append(cb)

    def retheme(self):
        mode = self.pal.toggle()
        ctk.set_appearance_mode(mode)
        # drop dead widgets, re-apply the rest
        alive = []
        for w, roles in self.themed:
            try:
                w.winfo_exists()
            except Exception:
                continue
            self._apply(w, roles)
            alive.append((w, roles))
        self.themed = alive
        for cb in list(self.dynamic):
            try:
                cb()
            except Exception:
                pass
        return mode

    # ── widget factories ─────────────────────────────────────────────────
    def frame(self, parent, fg="surface", border=None, bw=0, corner=11, **kw):
        f = ctk.CTkFrame(parent, corner_radius=corner, border_width=bw, **kw)
        roles = {}
        if fg is not None:
            roles["fg_color"] = fg
        if border is not None:
            roles["border_color"] = border
        return self.reg(f, **roles)

    def label(self, parent, text="", color="text", font=None, fg_color=None, **kw):
        lbl = ctk.CTkLabel(parent, text=text, font=font or self.f_base, **kw)
        roles = {"text_color": color}
        if fg_color is not None:
            roles["fg_color"] = fg_color
        return self.reg(lbl, **roles)

    def button(self, parent, text="", kind="accent", command=None, width=0,
               height=34, font=None, corner=8, **kw):
        fg, txt, hov, bd = _BTN_KINDS[kind]
        b = ctk.CTkButton(parent, text=text, command=command, height=height,
                          corner_radius=corner, font=font or self.f_btn, **kw)
        if width:
            b.configure(width=width)
        roles = {"fg_color": fg, "text_color": txt, "hover_color": hov}
        if bd is not None:
            b.configure(border_width=1)
            roles["border_color"] = bd
        return self.reg(b, **roles)

    def entry(self, parent, textvariable=None, placeholder="", field="win",
              mono=False, height=32, width=0, **kw):
        e = ctk.CTkEntry(parent, textvariable=textvariable, placeholder_text=placeholder,
                         height=height, corner_radius=7,
                         font=self.f_mono if mono else self.f_small, **kw)
        if width:
            e.configure(width=width)
        return self.reg(e, fg_color=field, border_color="border",
                        text_color="text", placeholder_text_color="text3")

    def option(self, parent, values, variable=None, command=None, field="surface",
               width=160, height=32, font=None):
        o = ctk.CTkOptionMenu(parent, values=values, variable=variable, command=command,
                              width=width, height=height, corner_radius=7,
                              font=font or self.f_small, dynamic_resizing=False)
        return self.reg(o, fg_color=field, button_color=field, button_hover_color="surface3",
                        text_color="text", dropdown_fg_color="surface2",
                        dropdown_text_color="text", dropdown_hover_color="surface3")

    def check(self, parent, text="", variable=None, command=None, color="text2"):
        cb = ctk.CTkCheckBox(parent, text=text, variable=variable, command=command,
                             font=self.f_small, checkbox_width=17, checkbox_height=17,
                             corner_radius=4)
        return self.reg(cb, fg_color="accent", hover_color="accent", border_color="border",
                        checkmark_color="#ffffff", text_color=color)

    def textbox(self, parent, height=96, **kw):
        t = ctk.CTkTextbox(parent, height=height, corner_radius=9, font=self.f_mono,
                           border_width=1, wrap="word", **kw)
        return self.reg(t, fg_color="desk", border_color="border", text_color="text")


class StatusDot(tk.Canvas):
    """Small filled circle used in the status pill (colour set dynamically)."""

    def __init__(self, parent, kit, size=9):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.kit, self.size = kit, size
        self._oval = self.create_oval(1, 1, size - 1, size - 1, outline="")

    def set(self, color_key, bg_key):
        self.configure(bg=self.kit.color(bg_key))
        self.itemconfigure(self._oval, fill=self.kit.color(color_key))


class TabBar(ctk.CTkFrame):
    """Pill-style segmented tab group matching the design."""

    def __init__(self, parent, kit, items, initial, command, font=None):
        super().__init__(parent, corner_radius=9, border_width=1)
        self.kit = kit
        self.command = command
        self.active = initial
        self.font = font or kit.f_pill
        kit.reg(self, fg_color="titlebar", border_color="border")
        self.buttons = {}
        for tid, label in items:
            b = ctk.CTkButton(self, text=label, font=self.font, height=30, corner_radius=7,
                              command=lambda t=tid: self._click(t))
            b.pack(side="left", padx=1, pady=3)
            self.buttons[tid] = b
        kit.add_dynamic(self._restyle)
        self._restyle()

    def _click(self, tid):
        self.active = tid
        self._restyle()
        self.command(tid)

    def select(self, tid):
        self.active = tid
        self._restyle()

    def _restyle(self):
        for tid, b in self.buttons.items():
            on = tid == self.active
            b.configure(
                fg_color=self.kit.color("accent") if on else "transparent",
                hover_color=self.kit.color("accent_h") if on else self.kit.color("ghost_h"),
                text_color=self.kit.color("on_accent") if on else self.kit.color("text2"),
            )
