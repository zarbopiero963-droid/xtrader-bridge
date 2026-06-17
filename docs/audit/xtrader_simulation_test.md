# Test end-to-end in simulazione — XTrader Signal Bridge

> PR-20 (PHASE 9). Procedura **manuale** per verificare la catena completa
> Telegram → bridge → CSV → XTrader → conferma, con XTrader in **Modalità
> Simulazione**. Questi passi NON sono eseguibili in ambiente headless: vanno
> svolti dal proprietario su Windows. Stake basso, limiti chiari, nessuna
> promessa di profitto.

## 0. Premesse di sicurezza

> **Comportamento ATTUALE di DRY_RUN (importante).** Il flag `dry_run` esiste in
> config (default = simulazione) e la logica `safety_guard` è testata, ma il
> **wiring runtime non è ancora attivo** (`TODO(wiring)`, vedi `final_audit.md` §4):
> oggi il bridge **non** modifica ancora il proprio comportamento di scrittura in
> base a `dry_run`. Per questo, durante il collaudo, la sicurezza è garantita da
> **XTrader in Modalità Simulazione**, non dal flag del bridge. I passi "atteso"
> che menzionano DRY_RUN descrivono il comportamento **desiderato dopo il wiring**;
> sono segnalati di volta in volta.

- XTrader in **Modalità Simulazione** (mai reale durante il collaudo) — è questa,
  oggi, la garanzia primaria.
- Bridge in **DRY_RUN** in config; passare a modalità reale solo consapevolmente,
  con stake minimo e **dopo** che il wiring runtime è stato implementato e verificato.
- Usare un bot Telegram e una chat **di test**, non quelli di produzione.

> **Cosa è agganciato al runtime oggi** (vedi `final_audit.md` §4). Sono attivi:
> filtro chat (solo con `chat_id` configurato), parsing+validazione, scrittura/
> svuotamento CSV. **NON sono ancora agganciati** (logica pura testata, non collegata
> al bot live): protezione **duplicati/raffica** (Caso E), **conferma XTrader** (Caso F),
> **DRY_RUN/limite-giorno**, **multi-chat** provider/mode. I passi "atteso" che li
> riguardano sono marcati `TODO(wiring)` e oggi **falliranno**: vanno trattati come
> verifica del **comportamento desiderato dopo il wiring**, non come criteri superabili ora.

## 1. Setup

1. Avvia l'EXE (o `python main.py` in dev).
2. Configura: token bot di test, `chat_id` della chat sorgente di test, percorso
   CSV concordato con XTrader, timeout di auto-clear.
3. Verifica che la config sia salvata in `%APPDATA%\XTraderBridge\config.json`.
4. In XTrader: configura la fonte "Segnali" a leggere lo stesso CSV, lingua
   **italiana** (per il match NAME_ONLY), Modalità Simulazione.

## 2. Caso A — segnale valido (happy path)

> **Nota DRY_RUN.** Oggi il flag non è agganciato: il bridge **scrive** comunque la riga
> (la sicurezza è data da XTrader in Simulazione). Una volta agganciato il wiring, DRY_RUN
> **sopprimerà** la scrittura operativa. Per non avere un criterio contraddittorio, il
> test di scrittura+XTrader (A1) va eseguito con **DRY_RUN disattivato** (modalità reale
> ma XTrader in Simulazione); un separato **smoke DRY_RUN (A2)** verifica la non-scrittura
> dopo il wiring.

### A1 — scrittura + lettura XTrader (DRY_RUN OFF, XTrader in Simulazione)
1. Avvia il bridge (START).
2. Invia nella chat di test un messaggio P.Bet. valido, oppure coerente col Parser
   Personalizzato attivo.
3. **Atteso nel bridge:** segnale riconosciuto, validato, scritto nel CSV.
4. **Atteso nel CSV:** header a 14 colonne + **una** riga; `BetType` PUNTA/BANCA;
   `Handicap`=0; `Points` vuoto; encoding `utf-8-sig`.
5. **Atteso in XTrader:** la fonte Segnali legge il CSV; segnale valido (verde) secondo
   `MarketId+SelectionId` o `EventName+MarketType+SelectionName`.

### A2 — `TODO(wiring)` smoke DRY_RUN (dopo il wiring di PR-19)
1. Con `dry_run` attivo, invia lo stesso segnale valido.
2. **Atteso (dopo wiring):** **nessuna** scrittura del CSV operativo; log che indica la
   simulazione. *Oggi questo passo fallisce perché il flag non è agganciato.*

## 3. Caso B — segnale invalido (deve essere scartato)

1. Invia un messaggio senza quota / con quota ≤ 1.0 / senza squadre.
2. **Atteso:** nessuna riga scritta; motivo dello scarto a log; CSV invariato.

## 4. Caso C — chat non autorizzata (deve essere ignorata)

> **Pre-requisito:** in config deve esserci un `chat_id` esplicito (o un override
> `parser_by_chat`). Con config vuota il filtro ammette **tutte** le chat (vedi
> `final_audit.md` §4 punto 6) e questo caso non è valido.

1. Con un `chat_id` configurato, invia un messaggio da una chat **diversa**.
2. **Atteso:** messaggio ignorato; nessuna scrittura; log coerente.

## 5. Caso D — svuotamento (auto-clear)

1. Dopo un segnale valido, attendi il timeout configurato.
2. **Atteso:** il CSV viene svuotato lasciando **solo l'header** (nessun vecchio
   segnale residuo).

## 6. Caso E — `TODO(wiring)` duplicati e raffica (NON ancora attivo)

> `signal_dedupe`/`DailyLimiter` non sono agganciati a `app` (vedi `final_audit.md`
> §4 punti 1–2): **oggi due messaggi identici ravvicinati riscrivono il CSV due
> volte** e la raffica non è limitata. Questo caso descrive il comportamento
> **desiderato dopo il wiring** e oggi **fallisce**.

1. Invia due volte lo **stesso** messaggio ravvicinato.
2. **Atteso (dopo wiring):** il secondo è riconosciuto come duplicato (nessuna seconda
   scommessa).
3. Invia molti segnali in poco tempo.
4. **Atteso (dopo wiring):** oltre il limite/minuto e il limite/giorno i segnali in
   eccesso sono rifiutati.

## 7. Caso F — `TODO(wiring)` conferma XTrader (NON ancora attivo)

> `confirmation_reader`/`signal_queue` non sono usati da `app` (vedi `final_audit.md`
> §4 punti 3–4): **oggi una notifica XTrader non marca alcun segnale**. Caso
> descrittivo del comportamento desiderato dopo il wiring; oggi **fallisce**.

1. Con XTrader configurato per notificare l'esito su una chat **separata**
   (`xtrader_notification_chat_id`), lascia che XTrader elabori il segnale in
   simulazione.
2. **Atteso (dopo wiring):** il bridge interpreta la notifica e marca il segnale
   CONFIRMED / REJECTED / (TIMEOUT se nessuna conferma entro il tempo). La conferma
   **non** genera una nuova scommessa.

## 8. Caso G — riavvio

1. Riavvia il bridge e l'EXE.
2. **Atteso:** la config persiste; nessun thread/polling incoerente dopo STOP/chiusura.
   (Il riconoscimento dei duplicati dopo riavvio dipende dal wiring di `signal_dedupe`,
   oggi non attivo — vedi Caso E.)

## 9. Esito

- [ ] Casi **attivi oggi** con esito atteso: A1, B, C (con `chat_id`), D, G.
- [ ] Casi `TODO(wiring)` (A2, E, F): verificati **dopo** l'aggancio al runtime; oggi
      attesi come falliti/non applicabili. Non certificarli come superati prima del wiring.
- [ ] Nessun token nei log; nessun CSV corrotto/parziale; header sempre presente.
- [ ] Registrare versione testata, data, ambiente (Windows/XTrader) e note.

> Se un caso fallisce, NON passare alla modalità reale: annota il comportamento,
> apri un'issue e correggi prima di rilasciare.
