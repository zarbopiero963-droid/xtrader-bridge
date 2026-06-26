"""Test hard del sync palinsesto Betfair (issue #86 PR-P6).

Parsing del navigation menu (filtro sport) e del listMarketCatalogue, e sync nel
dizionario locale con transport finti (offline): per sport, idempotente (due volte
non duplica), read-only. Nessuna chiamata di rete, nessun XTrader.
"""

import pytest

from xtrader_bridge.betfair import safety
from xtrader_bridge.betfair.catalogue_client import (
    CatalogueSync,
    SPORTS_EVENT_TYPE,
    event_type_ids_for,
    parse_market_catalogue,
    parse_navigation,
    split_participants,
)
from xtrader_bridge.betfair.local_db import BetfairLocalDB


@pytest.fixture()
def db():
    d = BetfairLocalDB(":memory:")
    yield d
    d.close()


# ── helpers di parsing ────────────────────────────────────────────────────────

def test_event_type_ids_for():
    assert event_type_ids_for(["Calcio", "Tennis"]) == {"1", "2"}
    assert event_type_ids_for(["Sconosciuto"]) == set()
    assert SPORTS_EVENT_TYPE["Rugby Union"] == "5"


def test_split_participants():
    assert split_participants("Inter v Milan") == ("Inter", "Milan")
    assert split_participants("Sinner vs Alcaraz") == ("Sinner", "Alcaraz")
    assert split_participants("ATP Finals") == ("ATP Finals", "")
    assert split_participants("") == ("", "")


# ── navigation menu ───────────────────────────────────────────────────────────

def _menu():
    return {
        "type": "GROUP", "name": "ROOT", "children": [
            {"type": "EVENT_TYPE", "id": "1", "name": "Soccer", "children": [
                {"type": "COMPETITION", "id": "c1", "name": "Serie A", "children": [
                    {"type": "EVENT", "id": "e1", "name": "Inter v Milan",
                     "openDate": "2026-07-01T18:00:00Z", "children": [
                        {"type": "MARKET", "id": "1.101", "name": "Match Odds",
                         "marketType": "MATCH_ODDS"}]}]}]},
            {"type": "EVENT_TYPE", "id": "2", "name": "Tennis", "children": [
                {"type": "EVENT", "id": "e2", "name": "Sinner v Alcaraz", "children": [
                    {"type": "MARKET", "id": "1.202", "name": "Match Odds",
                     "marketType": "MATCH_ODDS"}]}]},
            {"type": "EVENT_TYPE", "id": "999", "name": "Cricket", "children": [
                {"type": "EVENT", "id": "e9", "name": "X v Y", "children": [
                    {"type": "MARKET", "id": "1.900", "name": "Match Odds"}]}]},
        ]}


def test_parse_navigation_filtra_sport():
    # Solo Calcio (1): niente Tennis, niente Cricket.
    recs = parse_navigation(_menu(), {"1"})
    assert len(recs) == 1
    r = recs[0]
    assert r["event_type"]["id"] == "1"
    assert r["competition"]["name"] == "Serie A"
    assert r["event"]["id"] == "e1"
    assert r["market"]["id"] == "1.101"


def test_parse_navigation_sport_non_ammessi_scartati():
    # Calcio+Tennis ammessi, Cricket (999) scartato.
    recs = parse_navigation(_menu(), {"1", "2"})
    ids = {r["market"]["id"] for r in recs}
    assert ids == {"1.101", "1.202"}


# ── market catalogue ──────────────────────────────────────────────────────────

def _catalogue():
    return [
        {"marketId": "1.101", "marketName": "Match Odds",
         "description": {"marketType": "MATCH_ODDS"},
         "event": {"id": "e1", "name": "Inter v Milan"},
         "runners": [
             {"selectionId": 47972, "runnerName": "Inter", "handicap": 0},
             {"selectionId": 47973, "runnerName": "Milan", "handicap": 0},
             {"selectionId": 58805, "runnerName": "The Draw", "handicap": 0}]},
    ]


def test_parse_market_catalogue():
    out = parse_market_catalogue(_catalogue())
    assert "1.101" in out
    info = out["1.101"]
    assert info["market_type"] == "MATCH_ODDS"
    assert len(info["runners"]) == 3
    assert info["runners"][0]["selection_id"] == "47972"


# ── sync end-to-end nel DB locale ─────────────────────────────────────────────

def _sync(db):
    return CatalogueSync(db, navigation_transport=lambda: _menu(),
                         catalogue_transport=lambda mids: _catalogue())


def test_sync_persiste_sport_evento_mercato_selezioni(db):
    summary = _sync(db).sync(["Calcio"])
    assert db.count_active("betfair_sports") == 1
    assert db.count_active("betfair_events") == 1
    assert db.count_active("betfair_markets") == 1
    assert db.count_active("betfair_selections") == 3   # Inter/Milan/The Draw
    # participant_1/participant_2 salvati dall'evento "Inter v Milan"
    ev = db.get_events()[0]
    assert ev["participant_1"] == "Inter" and ev["participant_2"] == "Milan"
    assert summary["selections"] == 3


def test_sync_due_volte_non_duplica(db):
    s = _sync(db)
    s.sync(["Calcio"])
    s.sync(["Calcio"])                       # stessa identica risposta
    assert db.count_active("betfair_sports") == 1
    assert db.count_active("betfair_events") == 1
    assert db.count_active("betfair_markets") == 1
    assert db.count_active("betfair_selections") == 3


def test_sync_tennis(db):
    CatalogueSync(db, navigation_transport=lambda: _menu(),
                  catalogue_transport=lambda mids: []).sync(["Tennis"])
    # Solo Tennis: l'evento e2 c'è, il Calcio no.
    ids = {e["event_id"] for e in db.get_events()}
    assert ids == {"e2"}


def test_sync_marker_avanza_e_disattiva_record_spariti(db):
    s = _sync(db)
    s.sync(["Calcio"])
    # seconda sync: il menu non ha più il mercato 1.101 (evento sparito)
    empty = CatalogueSync(db, navigation_transport=lambda: {"type": "GROUP", "children": [
        {"type": "EVENT_TYPE", "id": "1", "name": "Soccer", "children": []}]},
        catalogue_transport=lambda mids: [])
    empty.sync(["Calcio"])
    assert db.count_active("betfair_events") == 0      # evento non più visto → inattivo
    assert db.count_active("betfair_markets") == 0


def test_sync_un_solo_sport_non_disattiva_altri(db):
    # Sync Calcio+Tennis, poi sync solo Calcio: il Tennis resta attivo.
    _sync(db).sync(["Calcio", "Tennis"])
    assert db.count_active("betfair_events") == 2
    _sync(db).sync(["Calcio"])               # ri-sincronizza solo Calcio
    ids = {e["event_id"]: e["active"] for e in db.get_events()}
    assert ids["e1"] == 1     # Calcio rivisto
    assert ids["e2"] == 1     # Tennis NON toccato (fuori scope)


# ── read-only: nessuna operazione di scommessa ────────────────────────────────

def test_sync_operazioni_sono_read_only():
    # Le operazioni dichiarate dal client non sono di scommessa.
    from xtrader_bridge.betfair import catalogue_client as cc
    assert safety.is_forbidden_betting_op(cc.NAVIGATION_OP) is False
    assert safety.is_forbidden_betting_op(cc.CATALOGUE_OP) is False


def test_sync_passa_dal_guard_read_only(db, monkeypatch):
    # Se il guard iniziasse a considerare vietata un'operazione del sync, sync alza.
    monkeypatch.setattr(safety, "is_forbidden_betting_op", lambda op: True)
    with pytest.raises(safety.ReadOnlyViolation):
        _sync(db).sync(["Calcio"])
