"""XTrader Signal Bridge — redesigned GUI (native CustomTkinter).

Faithful native reimplementation of the "XTrader Bridge" design handoff:
professional dense trading/fintech look, dark + light themes with a switch,
window chrome-free native shell, no emoji (clean text/vector glyphs), and the
same live interactions as the design prototype (AVVIA/STOP state machine,
typed-REALE confirmation, multi-signal confirm, live Parser test, etc.).

Run with:  python -m xtrader_bridge_gui
"""

from .theme import Palette, build_palette  # noqa: F401

__version__ = "0.1.0"
