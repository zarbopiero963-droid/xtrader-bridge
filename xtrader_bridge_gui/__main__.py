"""Run the redesigned XTrader Bridge GUI.

    python -m xtrader_bridge_gui           # launch the app
    python -m xtrader_bridge_gui --smoke   # headless construction self-test
"""

from __future__ import annotations

import sys

from .app import App


def _smoke(app: App):
    """Exercise every window/tab/modal once and report failures."""
    errors = []

    def step(desc, fn):
        try:
            fn()
            app.update()
            app.update_idletasks()
        except Exception as exc:  # noqa: BLE001
            import traceback
            errors.append(f"{desc}: {exc}\n{traceback.format_exc()}")

    step("config tabs", lambda: [app._set_cfg_tab(t) for t in ("gen", "rec", "safe", "conf")])
    step("monitor tabs", lambda: [app._set_mon_tab(t) for t in ("chats", "stato", "dash", "log")])
    step("start", app.start)
    step("sim event", app._sim_event)
    step("stop", app.stop)
    step("theme toggle", app.toggle_theme)
    step("theme toggle back", app.toggle_theme)
    step("open tools", app.open_tools)
    tw = app.tools_win
    step("tool tabs", lambda: [tw._show_tab(t) for t in
                               ("parser", "src", "prov", "prof", "map", "sync", "diz", "parser")])
    step("parser run test", tw._run_test)
    step("insert fixed", tw.insert_fixed)
    step("multimarket on", lambda: (tw.mm_var.set(True), tw._toggle_mm()))
    step("add market", tw._add_market)
    step("multiselection on", lambda: (tw.ms_var.set(True), tw._toggle_ms()))
    step("add selection", tw._add_selection)
    step("save parser", lambda: (tw.p_name.set("VIP_Over"), tw.p_save()))
    step("new parser", tw.p_new)
    step("load parser", lambda: (tw.p_selected.set("VIP_Over"), tw.p_load()))
    step("map subtabs", lambda: [tw._set_map_tab(t) for t in ("teams", "markets", "teams")])
    step("add provider", lambda: (tw.new_provider.set("Alpha"), tw._add_provider()))
    step("add source", tw._add_source)
    step("open dict markets", lambda: tw._open_dict("markets"))
    step("open dict names", lambda: tw._open_dict("names"))

    from .dialogs import RealConfirm, MultiConfirm
    step("real confirm dialog", lambda: RealConfirm(app, lambda: None, lambda: None))
    step("multi confirm dialog", lambda: MultiConfirm(app, "APPEND_ACTIVE", lambda: None))

    if errors:
        print("SMOKE FAILURES:")
        for e in errors:
            print(" -", e)
        return 1
    print("SMOKE OK — all windows/tabs/modals constructed without error.")
    return 0


def main():
    smoke = "--smoke" in sys.argv
    app = App(smoke=smoke)
    if smoke:
        code = 0

        def run():
            nonlocal code
            code = _smoke(app)
            app.after(200, app.destroy)
        app.after(300, run)
        app.mainloop()
        sys.exit(code)
    else:
        app.mainloop()


if __name__ == "__main__":
    main()
