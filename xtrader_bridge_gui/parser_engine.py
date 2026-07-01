"""Pure Parser test engine — ported 1:1 from the design prototype's JS.

Kept free of any GUI dependency so it can be unit-tested headless, mirroring
the real project's rule that parsing logic lives outside the GUI.
"""

from __future__ import annotations

import re

CSV_COLS = [
    "Provider", "EventId", "EventName", "MarketId", "MarketName", "MarketType",
    "SelectionId", "SelectionName", "Handicap", "Price", "MinPrice", "MaxPrice",
    "BetType", "Points",
]

TRANSFORMS = ["", "over_somma", "upper", "lower", "strip", "to_float"]
VALUEMAPS = ["", "markettype", "marketname", "selectionname", "bettype", "dizionario"]

# XTrader demo catalogue: label -> suggested fixed rules
CATALOG = {
    "Entrambe le squadre a segno": {"market": "BOTH_TEAMS_TO_SCORE", "sel": "Yes", "bet": "PUNTA"},
    "Esito finale 1X2": {"market": "MATCH_ODDS", "sel": "", "bet": "PUNTA"},
    "Under/Over 2.5": {"market": "OVER_UNDER_25", "sel": "Over 2.5 Goals", "bet": "PUNTA"},
    "Prossimo goal": {"market": "NEXT_GOAL", "sel": "", "bet": "PUNTA"},
}

DEFAULT_MSG = (
    "SEGNALE LIVE\nPartita: Inter v Milan\nMercato: OVER 2.5\n"
    "Selezione: Over 2.5 Goals\nQuota: 1.85\nTipo: PUNTA\n"
)


def default_rules() -> list[dict]:
    preset = {
        "Provider": {"fx": "TelegramBot"},
        "EventName": {"sa": "Partita: ", "eb": "\n", "req": True},
        "MarketName": {"sa": "Mercato: ", "eb": "\n", "vm": "marketname"},
        "MarketType": {"sa": "Mercato: ", "eb": "\n", "vm": "markettype", "req": True},
        "SelectionName": {"sa": "Selezione: ", "eb": "\n", "vm": "selectionname", "req": True},
        "Price": {"sa": "Quota: ", "eb": "\n", "tr": "to_float"},
        "BetType": {"sa": "Tipo: ", "eb": "\n", "vm": "bettype"},
        "Handicap": {"fx": "0"},
    }
    rules = []
    for col in CSV_COLS:
        base = {"col": col, "sa": "", "eb": "", "fx": "", "tr": "", "vm": "", "req": False}
        base.update(preset.get(col, {}))
        rules.append(base)
    return rules


def apply_transform(v, tr):
    if v is None:
        return v
    if tr == "upper":
        return v.upper()
    if tr == "lower":
        return v.lower()
    if tr == "strip":
        return v.strip()
    if tr == "to_float":
        m = re.search(r"[0-9]+(\.[0-9]+)?", str(v).replace(",", "."))
        return m.group(0) if m else v
    if tr == "over_somma":
        nums = [float(x.replace(",", ".")) for x in re.findall(r"[0-9]+(?:[.,][0-9]+)?", str(v))]
        return str(sum(nums)) if nums else v
    return v


def _extract(msg, r):
    if r.get("fx"):
        return r["fx"]
    sa, eb = r.get("sa", ""), r.get("eb", "")
    if not sa and not eb:
        return ""
    start = 0
    if sa:
        i = msg.find(sa)
        if i < 0:
            return None
        start = i + len(sa)
    end = len(msg)
    if eb:
        j = msg.find(eb, start)
        if j < 0:
            return None
        end = j
    return msg[start:end].strip()


def _extract_cut(msg, after, before):
    if not after and not before:
        return ""
    start = 0
    if after:
        i = msg.find(after)
        if i < 0:
            return None
        start = i + len(after)
    end = len(msg)
    if before:
        j = msg.find(before, start)
        if j < 0:
            return None
        end = j
    return msg[start:end].strip()


def run_test(msg, rules, multi_market, market_rows, multi_selection, selection_rows):
    """Return (gen_rows, diag, verdict) exactly like the prototype's _runTest."""
    base, missing, diag = {}, [], []
    for r in rules:
        v = _extract(msg, r)
        if v is not None and v != "" and r.get("tr"):
            v = apply_transform(v, r["tr"])
        ok = v is not None and v != ""
        if r.get("req") and not ok and r["col"] not in missing:
            missing.append(r["col"])
        base[r["col"]] = "" if v is None else v
        if v is None:
            status = "Assente" if r.get("req") else "—"
            color = "danger" if r.get("req") else "text3"
        elif v == "":
            status = "Vuoto" if r.get("req") else "—"
            color = "danger" if r.get("req") else "text3"
        else:
            status, color = "OK", "success"
        diag.append({"col": r["col"], "status": status, "color": color,
                     "val": "—" if (v is None or v == "") else v})

    # expand into markets × selections
    variants = [{}]
    if multi_market and market_rows:
        variants = []
        for m in market_rows:
            cut = _extract_cut(msg, m.get("after", ""), m.get("before", "")) \
                if (m.get("after") or m.get("before")) else None
            match = (not m.get("text")) or (cut is not None and m["text"].lower() in cut.lower())
            variants.append({"MarketType": m.get("market", ""), "_match": match})

    rows = []
    for v in variants:
        if multi_selection and selection_rows:
            for sel in selection_rows:
                sv = sel.get("sel") or (
                    _extract_cut(msg, sel.get("after", ""), sel.get("before", ""))
                    if (sel.get("after") or sel.get("before")) else "")
                row = {**base, **v, "SelectionName": sv or base.get("SelectionName", "")}
                rows.append(row)
        else:
            rows.append({**base, **v})
    if not rows:
        rows = [dict(base)]

    gen_rows = []
    for i, row in enumerate(rows):
        row_missing = [r["col"] for r in rules
                       if r.get("req") and not (row.get(r["col"]) and str(row[r["col"]]).strip())]
        ok = len(row_missing) == 0
        summary = "  ·  ".join(f"{c}={row[c]}" for c in CSV_COLS
                               if row.get(c) and str(row[c]).strip()) or "(nessun campo)"
        gen_rows.append({"idx": i + 1, "esito": "Piazzabile" if ok else "Scartata",
                         "color": "success" if ok else "danger", "summary": summary})

    ok_count = sum(1 for g in gen_rows if g["esito"] == "Piazzabile")
    if ok_count == len(gen_rows) and ok_count > 0:
        verdict = {"text": f"Pronto — {len(gen_rows)} riga/e generata/e, tutte piazzabili.",
                   "color": "success", "bg": "success_weak", "icon": "check"}
    else:
        uniq = list(dict.fromkeys(missing))
        if uniq:
            text = f"Non pronto — mancano campi obbligatori: {', '.join(uniq)}."
        else:
            text = f"Attenzione — {len(gen_rows) - ok_count} di {len(gen_rows)} righe non piazzabili."
        verdict = {"text": text, "color": "danger", "bg": "danger_weak", "icon": "alert"}
    return gen_rows, diag, verdict
