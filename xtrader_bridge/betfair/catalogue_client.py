"""Sync del palinsesto Betfair: navigation menu + listMarketCatalogue (issue #86 PR-P6).

Scarica il **navigation menu** Betfair (read-only) filtrando gli sport del blocco
personale (Calcio, Tennis, Basket, Rugby Union), poi **arricchisce** i mercati con
`listMarketCatalogue` (MarketId, SelectionId, nome selezione, handicap, market type,
nome evento, participant_1/2) e salva tutto nel **dizionario locale** (`BetfairLocalDB`).

Vincoli (issue #86):
- usa la **Delayed App Key** (mai la Live Key); legge solo, niente quote live se non
  necessarie;
- **nessuna operazione di scommessa**: ogni operazione passa dal guard
  `safety.assert_read_only`, che blocca le operazioni di scommessa dell'Exchange;
- nessun dato sensibile nei log; i token restano in RAM (`BetfairSession`).

Le chiamate di rete sono **iniettabili** (`navigation_transport`, `catalogue_transport`)
così i test girano offline con mock; il default usa la stdlib (urllib) ed è verificato
a mano. Il parsing del menu/catalogue è puro e testato.
"""

import json

from . import safety
from .local_db import BetfairLocalDB

# Sport del blocco personale → event_type_id ufficiale Betfair.
SPORTS_EVENT_TYPE = {
    "Calcio": "1",
    "Tennis": "2",
    "Basket": "7522",
    "Rugby Union": "5",
}

# Operazioni Betfair usate da questo client: SOLO lettura (nomi per il guard/log).
NAVIGATION_OP = "navigationMenu"
CATALOGUE_OP = "listMarketCatalogue"

_NAV_URL = "https://api.betfair.com/exchange/betting/rest/v1/en/navigation/menu.json"
_CATALOGUE_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"
_HTTP_TIMEOUT = 30


def event_type_ids_for(sports) -> set:
    """Insieme degli `event_type_id` per i nomi sport richiesti (ignota → scartata)."""
    out = set()
    for s in sports or ():
        etid = SPORTS_EVENT_TYPE.get(s)
        if etid:
            out.add(etid)
    return out


def split_participants(event_name):
    """(`participant_1`, `participant_2`) dal nome evento Betfair «Home v Away».

    Betfair separa i due partecipanti con `" v "`. Se non c'è separatore (es. una
    gara/torneo), ritorna (`nome`, ``""``). Input vuoto → (``""``, ``""``)."""
    name = (event_name or "").strip()
    if not name:
        return "", ""
    for sep in (" v ", " vs ", " @ "):
        if sep in name:
            a, b = name.split(sep, 1)
            return a.strip(), b.strip()
    return name, ""


def parse_navigation(menu, allowed_event_type_ids):
    """Estrae dal navigation menu i mercati degli sport ammessi.

    Ritorna una lista di record: ``{event_type, competition, event, market}`` (i
    primi tre possono essere parziali). Cammina ricorsivamente l'albero
    (EVENT_TYPE → GROUP* → COMPETITION? → EVENT → MARKET): i sottoalberi di sport
    non ammessi sono saltati interamente, così si salvano SOLO gli sport scelti."""
    allowed = {str(x) for x in (allowed_event_type_ids or ())}
    records = []

    def walk(node, etype=None, comp=None, event=None):
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        if ntype == "EVENT_TYPE":
            if str(node.get("id")) not in allowed:
                return  # sport non selezionato: salta tutto il sottoalbero
            etype = {"id": str(node.get("id")), "name": node.get("name")}
        elif ntype == "COMPETITION":
            comp = {"id": str(node.get("id")), "name": node.get("name")}
        elif ntype == "EVENT":
            event = {"id": str(node.get("id")), "name": node.get("name"),
                     "openDate": node.get("openDate")}
        elif ntype == "MARKET":
            if etype is not None:
                records.append({
                    "event_type": etype, "competition": comp, "event": event,
                    "market": {"id": str(node.get("id")), "name": node.get("name"),
                               "marketType": node.get("marketType")},
                })
        for child in node.get("children") or ():
            walk(child, etype, comp, event)

    walk(menu)
    return records


def parse_market_catalogue(catalogue):
    """Normalizza la risposta di `listMarketCatalogue` in una mappa
    ``market_id -> {event, market_type, runners:[{selection_id, runner_name,
    handicap}]}``. Tollerante a campi mancanti."""
    out = {}
    for item in catalogue or ():
        if not isinstance(item, dict):
            continue
        market_id = str(item.get("marketId") or "")
        if not market_id:
            continue
        desc = item.get("description") or {}
        event = item.get("event") or {}
        runners = []
        for r in item.get("runners") or ():
            runners.append({
                "selection_id": str(r.get("selectionId") or ""),
                "runner_name": r.get("runnerName"),
                "handicap": r.get("handicap", 0) or 0,
            })
        out[market_id] = {
            "market_name": item.get("marketName"),
            "market_type": desc.get("marketType"),
            "event": {"id": str(event.get("id") or ""), "name": event.get("name"),
                      "openDate": event.get("openDate")},
            "runners": runners,
        }
    return out


class CatalogueSync:
    """Orchestratore del download palinsesto → dizionario locale (read-only).

    `navigation_transport()` ritorna il JSON del menu; `catalogue_transport(market_ids)`
    ritorna la lista `listMarketCatalogue`. Entrambi iniettabili per i test."""

    def __init__(self, db: BetfairLocalDB, *, navigation_transport=None,
                 catalogue_transport=None):
        self.db = db
        self._nav = navigation_transport
        self._cat = catalogue_transport

    def sync(self, sports) -> dict:
        """Sincronizza gli sport richiesti nel dizionario locale e ritorna un
        riepilogo safe. Idempotente: rieseguire con gli stessi dati non duplica
        (upsert per chiave naturale) e i record non più visti diventano inattivi."""
        # Contratto read-only: entrambe le operazioni NON sono di scommessa.
        safety.assert_read_only(NAVIGATION_OP)
        safety.assert_read_only(CATALOGUE_OP)

        marker = self.db.new_sync_marker()
        etids = event_type_ids_for(sports)

        menu = self._nav() if self._nav else {}
        records = parse_navigation(menu, etids)

        market_ids = []
        for rec in records:
            et = rec["event_type"]
            self.db.upsert_sport(et["id"], et.get("name"), seen_at=marker)
            comp = rec.get("competition")
            if comp and comp.get("id"):
                self.db.upsert_competition(comp["id"], et["id"], comp.get("name"),
                                           seen_at=marker)
            ev = rec.get("event")
            mk = rec["market"]
            if ev and ev.get("id"):
                p1, p2 = split_participants(ev.get("name"))
                self.db.upsert_event(ev["id"], et["id"],
                                     comp["id"] if comp and comp.get("id") else "",
                                     ev.get("name"), ev.get("openDate"), p1, p2,
                                     seen_at=marker)
            self.db.upsert_market(mk["id"], ev["id"] if ev else "", et["id"],
                                  mk.get("name"), mk.get("marketType"), seen_at=marker)
            if mk.get("id"):
                market_ids.append(mk["id"])

        # Arricchimento con il catalogue: selezioni del mercato. NB: non ri-upsertiamo
        # l'evento qui (il catalogue non porta l'event_type_id): lo sovrascriverebbe a
        # vuoto, rompendo lo scoping per sport. Nome/partecipanti vengono già dal menu.
        new_selections = 0
        synced_markets = []
        if market_ids and self._cat:
            catalogue = parse_market_catalogue(self._cat(market_ids))
            for market_id, info in catalogue.items():
                synced_markets.append(market_id)
                for r in info.get("runners", []):
                    if r.get("selection_id"):
                        self.db.upsert_selection(market_id, r["selection_id"],
                                                 r.get("runner_name"),
                                                 r.get("handicap", 0), seen_at=marker)
                        new_selections += 1

        # Record non più visti → inattivi. Sport/competizioni/eventi/mercati scoped per
        # sport (event_type_id) così un sport non tocca gli altri; le selezioni scoped
        # per ciascun mercato sincronizzato.
        for etid in etids:
            self.db.deactivate_unseen("betfair_sports", marker, scope_value=etid)
            self.db.deactivate_unseen("betfair_competitions", marker, scope_value=etid)
            self.db.deactivate_unseen("betfair_events", marker, scope_value=etid)
            self.db.deactivate_unseen("betfair_markets", marker, scope_value=etid)
        for market_id in synced_markets:
            self.db.deactivate_unseen("betfair_selections", marker, scope_value=market_id)

        summary = {
            "sports": sorted(etids),
            "markets": len(market_ids),
            "selections": new_selections,
            "active_events": self.db.count_active("betfair_events"),
            "active_markets": self.db.count_active("betfair_markets"),
        }
        self.db.record_sync_run(started_at=marker, finished_at=marker, status="OK",
                                summary=json.dumps(summary, ensure_ascii=False))
        return summary
