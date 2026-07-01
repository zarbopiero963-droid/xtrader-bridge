"""Tiny vector glyphs drawn on a Canvas (no emoji, theme-aware)."""

from __future__ import annotations

import tkinter as tk


class Glyph(tk.Canvas):
    def __init__(self, parent, kit, kind, size=16, color="text", bg="surface"):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.kit, self.kind, self.size = kit, kind, size
        self._color, self._bg = color, bg
        kit.add_dynamic(self.redraw)
        self.redraw()

    def set_bg(self, bg):
        self._bg = bg
        self.redraw()

    def set_color(self, color):
        self._color = color
        self.redraw()

    def redraw(self):
        self.delete("all")
        s = self.size
        c = self.kit.color(self._color)
        self.configure(bg=self.kit.color(self._bg))
        w = max(1.6, s / 11)
        if self.kind == "bridge":
            m = s * 0.16
            self.create_line(m, s / 2, s - m, s / 2, fill=c, width=w, capstyle="round")
            self.create_line(s * 0.30, s * 0.28, s * 0.30, s * 0.72, fill=c, width=w, capstyle="round")
            self.create_line(s * 0.50, s * 0.24, s * 0.50, s * 0.76, fill=c, width=w, capstyle="round")
            self.create_line(s * 0.70, s * 0.28, s * 0.70, s * 0.72, fill=c, width=w, capstyle="round")
            self.create_arc(m, s * 0.20, s - m, s * 0.80, start=20, extent=140,
                            style="arc", outline=c, width=w)
        elif self.kind == "sun":
            r = s * 0.24
            cx = cy = s / 2
            self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=c, width=w)
            import math
            for i in range(8):
                a = i * math.pi / 4
                x1 = cx + math.cos(a) * r * 1.7
                y1 = cy + math.sin(a) * r * 1.7
                x2 = cx + math.cos(a) * r * 2.3
                y2 = cy + math.sin(a) * r * 2.3
                self.create_line(x1, y1, x2, y2, fill=c, width=w, capstyle="round")
        elif self.kind == "moon":
            r = s * 0.34
            cx = cy = s / 2
            self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=c, width=w)
            off = s * 0.18
            self.create_oval(cx - r + off, cy - r - off * 0.2, cx + r + off, cy + r - off * 0.2,
                             outline="", fill=self.kit.color(self._bg))
