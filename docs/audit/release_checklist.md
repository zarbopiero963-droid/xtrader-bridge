# Checklist di release — XTrader Signal Bridge

> PR-20 (PHASE 9). Passi da eseguire **prima** di distribuire una versione. Il merge
> e la pubblicazione restano **manuali del proprietario**. Spunta ogni voce solo dopo
> averla verificata davvero.

## A. Pre-requisiti (ambiente di sviluppo)

- [ ] Branch pulito, allineato a `main`, nessun file fuori scope.
- [ ] Nessun segreto nello staging: niente `config.json` reale, token, chat ID reali,
      `.env`, CSV generati, log, EXE/ZIP (vedi `.gitignore`).

## B. Test automatici (offline)

- [ ] `python -m py_compile main.py` → OK.
- [ ] `python -m pytest -m "not manual"` → tutti verdi (atteso: 536 passed, 2 skipped
      o più, mai fallimenti).
- [ ] Il job CI `contract` è verde (contratto CSV a 14 colonne invariato).
- [ ] Tutti i check della PR sono **completati e verdi** prima del merge.

## C. Versione e changelog

- [ ] `xtrader_bridge.__version__` aggiornato secondo semver (oggi `0.1.0`).
- [ ] Il titolo della GUI mostra la versione corretta.
- [ ] README allineato al comportamento reale e al workflow (`build.yaml`).

## D. Build EXE Windows (manuale / CI Windows)

> Non eseguibile in ambiente headless. Eseguire su Windows o tramite il workflow
> `build.yaml` (push su `main` o tag `v*`).

- [ ] Il workflow `build.yaml` completa senza errori.
- [ ] L'artifact versionato `XTrader-Signal-Bridge-Windows-v<versione>-<data>.zip`
      è presente e scaricabile.
- [ ] L'EXE interno si chiama `XTrader-Signal-Bridge.exe` (nome stabile).
- [ ] L'EXE si avvia su Windows 10/11 senza terminale nero (`--windowed`).
- [ ] L'EXE **non** contiene token o config personali.
- [ ] L'EXE salva la config in `%APPDATA%\XTraderBridge\` e la ricarica al riavvio.
- [ ] L'EXE scrive il CSV nel percorso configurato.

## E. Sicurezza

- [ ] Tutte le GitHub Action nei workflow sono fissate a SHA (test di enforcement verde).
- [ ] Nessun token Telegram compare nei log (redazione attiva).
- [ ] DRY_RUN (simulazione) è il default per una config nuova/senza il campo.
- [ ] Limiti attivi: per-minuto (`signal_dedupe`) e per-giorno (`safety_guard`,
      una volta agganciato al runtime — vedi nota in `final_audit.md` §4).

## F. Verifica funzionale manuale (Windows + GUI)

- [ ] App avviabile; START/STOP funzionano; chiusura finestra ferma il bridge.
- [ ] Salvataggio config dalla GUI funziona e persiste.
- [ ] Log leggibile; errori parser/CSV visibili; nessun token mostrato.

## G. Simulazione XTrader

- [ ] Eseguita la procedura `xtrader_simulation_test.md` con XTrader in **Modalità
      Simulazione**, stake basso, limiti chiari. Esito atteso raggiunto.

## H. Rilascio

- [ ] Tag `v<versione>` creato (la release pubblica parte solo su tag).
- [ ] Note di release scritte (cosa cambia, limiti noti, avviso simulazione).
- [ ] Merge eseguito **manualmente** dal proprietario.

> Promemoria: nessuna promessa di profitto. Prima dell'uso reale, sempre simulazione,
> stake basso, limiti chiari, consapevolezza del rischio.
