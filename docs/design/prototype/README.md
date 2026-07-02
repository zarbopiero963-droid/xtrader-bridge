# Prototipo Claude Design — pacchetto originale (archivio)

Copia **versionata e immutabile** del pacchetto di design consegnato dal proprietario
il 1 luglio 2026 tramite «Claude Design → Claude Code», salvata qui su sua richiesta
esplicita (vedi issue #288/#293 e tracking #301, PR 2-ter) perché la sessione di
lavoro è effimera e il materiale non deve andare perso.

## Contenuto

| File | Cosa è |
|---|---|
| `XTrader Bridge.dc.html` | **Prototipo HTML interattivo originale** dell'intera UI (Claude Design). Aprire nel browser. |
| `XTrader Bridge-print-1lpxo2u.dc.html` | Versione stampa dello stesso prototipo. |
| `support.js` | File di supporto referenziato dal prototipo (export Claude Design). |
| `design_handoff_snapshot.md` | **Snapshot storico** del design handoff incluso nel pacchetto. ⚠️ NON è la fonte viva: quella è `docs/design/design_handoff.md`, che va tenuta allineata al codice (gate del repo). |
| `mockup_riordino_ui.html` | Mockup del riordino UI approvato dal proprietario (concept della issue #293: 4 gruppi di flusso, «Come lo scrive il canale», Traduzioni nel Parser, Riepilogo, blocco MultiMarket/MultiSelection preservato). Copia anche nel commento di #293. |
| `screenshots/*.png` | 13 screenshot dell'app (v0.1.0) forniti col pacchetto. Dati **vuoti o di test** (nessun token, nessun chat ID reale — verificato). Un 14° file era un duplicato byte-identico di `2.png` ed è stato omesso. |

## Cosa NON è

- Non è codice da eseguire o mergiare nell'app: **solo riferimento visivo** per le
  issue di design (#288 tema/placeholder/restyle, #293 riordino UI).
- Lo snapshot del handoff qui dentro **non va aggiornato**: è un archivio storico.
  Le modifiche al design correnti vivono in `docs/design/design_handoff.md`.

## Sicurezza

Il pacchetto è stato scansionato prima del commit: nessun token Telegram, nessun
chat ID reale (solo placeholder `-1001234567890` nel prototipo), screenshot con campi
vuoti o profilo «test».
