# Audit finale — XTrader Signal Bridge (Release Candidate)

> Documento di chiusura (PR-20, PHASE 9). Sintetizza lo stato del progetto dopo le
> PHASE 0–8 e mappa i problemi di `known_issues.md` alle PR che li hanno chiusi.
>
> **Onestà sui limiti:** questo audit è basato sull'analisi del codice e sui test
> automatici **offline** (headless). I passi che richiedono **Windows**, la **build
> EXE reale** o **XTrader live** NON sono eseguibili in questo ambiente e sono
> elencati come **verifiche manuali del proprietario** (vedi `release_checklist.md`
> e `xtrader_simulation_test.md`). Dove un esito non è stato verificato qui, è
> dichiarato esplicitamente "da verificare a mano", non "passato".

---

## 1. Esito sintetico

| Dimensione | Stato | Note |
|---|---|---|
| Contratto CSV XTrader (14 col) | ✅ Conforme | barriera di test `contract`; `utf-8-sig` + `QUOTE_ALL` |
| Parser (hardcoded + Parser Personalizzato) | ✅ Coperto da test | catena Telegram→riga validata, fail-closed |
| Validazione pre-scrittura | ✅ Implementata | nessun segnale invalido raggiunge il CSV |
| Telegram (filtro chat, hardening) | ✅ Implementato | filtro `chat_id` non permissivo, multi-chat |
| Config persistente (`%APPDATA%`) | ✅ Implementata | migrazione legacy + backup config corrotta |
| Scrittura CSV atomica + svuotamento | ✅ Implementata | tmp+rename, header sempre presente |
| Deduplica / coda / conferma | ✅ Logica pura testata | dedupe, coda multi-segnale, lettura conferme |
| Guardrail di sicurezza (DRY_RUN, limite/giorno) | ⚠️ Logica pronta, wiring runtime da agganciare | vedi §4 |
| Build EXE Windows (versionata) | ⚠️ Workflow pronto, build non eseguita qui | verifica manuale |
| Supply-chain (action SHA-pinned) | ✅ Implementato | test di enforcement |
| Test automatici | ✅ 536 passed, 2 skipped | vedi §3 |
| Segreti nel repo | ✅ Nessuno | `forbidden-files` + test no-secrets |

**Stato complessivo:** RELEASE CANDIDATE per i test in **simulazione**. Non è un via
libera all'uso reale: il merge resta manuale e l'uso operativo richiede le verifiche
manuali su Windows/XTrader e l'attivazione esplicita della modalità reale.

---

## 2. Mappa problemi (`known_issues.md`) → PR che li chiude

| # | Problema | Chiuso da | Stato |
|---|---|---|---|
| 1 | Validazione segnale prima del CSV | PR-01, PR-06, PR-10 | ✅ |
| 2 | Race write/clear | PR-05, PR-16 | ✅ |
| 3 | Parser P.Bet. senza emoji | PR-09 | ✅ |
| 4 | Formato CSV README vs codice | PR-01 | ✅ |
| 5 | Timestamp anti-duplicato | PR-01 (fuori CSV) + PR-15 | ✅ |
| 6 | Scrittura atomica / lock | PR-05 | ✅ |
| 7 | `.gitignore` mancante | PR-00 | ✅ |
| 8 | Filtro `chat_id` permissivo | PR-11, PR-12 | ✅ |
| 9 | `TELEGRAM_OK` mai controllato | PR-03, PR-11 | ✅ |
| 10 | Validazione input GUI | PR-13 | ✅ |
| 11 | Errori silenziati | PR-11, PR-14 | ✅ |
| 12 | Stake / MinPrice / MaxPrice | PR-01, PR-13 | ✅ (Stake gestito in XTrader) |
| 13 | Test automatici assenti | PR-02 + ogni PR | ✅ |
| 14 | README rotto/incoerente | PR-01, PR-18, PR-20 | ✅ |
| 15 | Build EXE | PR-18 | ⚠️ workflow pronto, build manuale |

---

## 3. Stato per area

### CSV (contratto)
- Header a 14 colonne in `csv_writer.CSV_HEADER`, order-sensitive; `BetType` ∈
  {PUNTA, BANCA}; `Handicap`=0; `Points` vuoto; `utf-8-sig` + `QUOTE_ALL`.
- Barriera di test `tests/unit/test_csv_contract.py` (job CI `contract`): diventa
  rossa se cambiano header/ordine/encoding/quoting o rientrano `Stake`/`Timestamp`.
- Scrittura atomica (`write_atomic`/tmp+rename) e svuotamento che mantiene l'header.

### Parser
- **Hardcoded** (`parser.py`): P.Bet. con/senza emoji, quota `,`/`.`, squadre `Home v Away`.
- **Parser Personalizzato** (CP-01…CP-10): regole configurabili (`start_after`/
  `end_before`), trasformazioni, value-map (dizionario + bettype), gate "Non pronto",
  routing per chat. Catena end-to-end testata in `tests/integration`.
- Fail-closed: un segnale incompleto/ambiguo NON produce una riga CSV.

### Mapping / dizionario
- `mapping.py`, `value_maps.py`, `dizionario.py`: alias Telegram → MarketType/
  SelectionName XTrader; alias ambigui scartati (mai una selezione tradotta a caso).

### Telegram
- `signal_router`, `source_manager`, `signal_gate`: filtro `chat_id` non permissivo
  (chat non approvata → ignorata), multi-chat con provider/mode, `drop_pending_updates`.
- `event_log`: log con **redazione dei segreti** (mai token Telegram nei log).

### Config
- `config_store`: `%APPDATA%\XTraderBridge\config.json`; migrazione legacy; backup
  `.bak` su config corrotta; default sicuri; chiavi additive senza rompere config vecchie.

### Sicurezza (PR-19)
- `safety_guard`: DRY_RUN (default sicuro = simulazione), warning modalità reale,
  `DailyLimiter` (limite/giorno UTC con reset) complementare al limite/minuto
  (`signal_dedupe`). **Vedi §4 sul wiring.**

### Build / supply-chain
- `build.yaml`: test → compile → PyInstaller `--windowed` → artifact **versionato**
  (`__version__` 0.1.0 + data); release solo su tag `v*`.
- Tutte le action dei workflow sono **fissate a SHA** (hardening) con test di enforcement.

### Test / coverage
- Vedi §below — 536 passed, 2 skipped (offline). I test live/manuali sono marcati `manual`.

```
unit         471 test
integration   17 test
safety        22 test
smoke         28 test
TOTALE       536 passed, 2 skipped (marcatore "manual" escluso)
```

---

## 4. Limiti noti / lavoro residuo (onesto)

1. **Wiring runtime di DRY_RUN (PR-19)**: la logica (`safety_guard`) e i default di
   config esistono e sono testati, ma **non sono ancora agganciati al flusso live**:
   oggi il blocco effettivo della scrittura del CSV operativo in simulazione, il
   banner di avviso e il collegamento del `DailyLimiter` al runtime restano da
   implementare e verificare a mano su Windows. **Finché non sono agganciati, il
   comportamento runtime è invariato.**
2. **GUI**: i controller sono testati headless, ma l'avvio GUI, START/STOP, salvataggio
   da finestra e builder del Parser Personalizzato vanno verificati a mano su Windows.
3. **Build EXE**: il workflow è pronto ma la build reale non è eseguibile qui.
4. **XTrader live**: lettura CSV, segnale verde, conferma Telegram → CONFIRMED sono
   passi manuali in **simulazione** (vedi `xtrader_simulation_test.md`).

---

## 5. Invarianti di sicurezza (verificate nei test offline)

- Nessun segnale invalido raggiunge il CSV (validator + gate).
- Una sola riga attiva quando il design è one-signal-at-a-time; header sempre presente.
- Filtro `chat_id` non indebolito; chat non approvata → ignorata.
- Nessun token/segreto nei log (redazione) né nel repo (`forbidden-files` + test).
- Contratto CSV invariato dalle PR successive a PR-01 (barriera `contract`).
- Merge sempre **manuale** del proprietario; nessun auto-merge.

---

## 6. Conclusione

Il progetto soddisfa gli obiettivi della roadmap per una **release candidate da
testare in simulazione**. Prima di qualunque uso reale: eseguire
`release_checklist.md` e `xtrader_simulation_test.md` su Windows con XTrader in
**Modalità Simulazione**, stake basso, limiti chiari. Nessuna promessa di profitto.
