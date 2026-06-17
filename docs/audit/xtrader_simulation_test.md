# Test end-to-end in simulazione — XTrader Signal Bridge

> PR-20 (PHASE 9). Procedura **manuale** per verificare la catena completa
> Telegram → bridge → CSV → XTrader → conferma, con XTrader in **Modalità
> Simulazione**. Questi passi NON sono eseguibili in ambiente headless: vanno
> svolti dal proprietario su Windows. Stake basso, limiti chiari, nessuna
> promessa di profitto.

## 0. Premesse di sicurezza

- XTrader in **Modalità Simulazione** (mai reale durante il collaudo).
- Bridge in **DRY_RUN** finché non si è verificata l'intera catena; passare a
  modalità reale solo consapevolmente e con stake minimo.
- Usare un bot Telegram e una chat **di test**, non quelli di produzione.

## 1. Setup

1. Avvia l'EXE (o `python main.py` in dev).
2. Configura: token bot di test, `chat_id` della chat sorgente di test, percorso
   CSV concordato con XTrader, timeout di auto-clear.
3. Verifica che la config sia salvata in `%APPDATA%\XTraderBridge\config.json`.
4. In XTrader: configura la fonte "Segnali" a leggere lo stesso CSV, lingua
   **italiana** (per il match NAME_ONLY), Modalità Simulazione.

## 2. Caso A — segnale valido (happy path)

1. Avvia il bridge (START).
2. Invia nella chat di test un messaggio P.Bet. valido (es. con squadre, quota,
   mercato), oppure un messaggio coerente con il Parser Personalizzato attivo.
3. **Atteso nel bridge:** segnale riconosciuto, validato, scritto nel CSV (in DRY_RUN
   la scrittura operativa è soppressa una volta agganciato il wiring — vedi
   `final_audit.md` §4; in modalità reale la riga viene scritta).
4. **Atteso nel CSV:** header a 14 colonne + **una** riga; `BetType` PUNTA/BANCA;
   `Handicap`=0; `Points` vuoto; encoding `utf-8-sig`.
5. **Atteso in XTrader:** la fonte Segnali legge il CSV; il segnale risulta valido
   (verde) secondo `MarketId+SelectionId` o `EventName+MarketType+SelectionName`.

## 3. Caso B — segnale invalido (deve essere scartato)

1. Invia un messaggio senza quota / con quota ≤ 1.0 / senza squadre.
2. **Atteso:** nessuna riga scritta; motivo dello scarto a log; CSV invariato.

## 4. Caso C — chat non autorizzata (deve essere ignorata)

1. Invia un messaggio da una chat NON configurata.
2. **Atteso:** messaggio ignorato; nessuna scrittura; log coerente.

## 5. Caso D — svuotamento (auto-clear)

1. Dopo un segnale valido, attendi il timeout configurato.
2. **Atteso:** il CSV viene svuotato lasciando **solo l'header** (nessun vecchio
   segnale residuo).

## 6. Caso E — duplicati e raffica

1. Invia due volte lo **stesso** messaggio ravvicinato.
2. **Atteso:** il secondo è riconosciuto come duplicato (non genera una seconda
   scommessa).
3. Invia molti segnali in poco tempo.
4. **Atteso:** oltre il limite/minuto (e, una volta agganciato, il limite/giorno) i
   segnali in eccesso sono rifiutati.

## 7. Caso F — conferma XTrader

1. Con XTrader configurato per notificare l'esito su una chat **separata**
   (`xtrader_notification_chat_id`), lascia che XTrader elabori il segnale in
   simulazione.
2. **Atteso:** il bridge interpreta la notifica e marca il segnale CONFIRMED /
   REJECTED / (TIMEOUT se nessuna conferma entro il tempo). La conferma **non**
   genera una nuova scommessa.

## 8. Caso G — riavvio

1. Riavvia il bridge e l'EXE.
2. **Atteso:** la config persiste; i duplicati recenti restano riconosciuti
   (history); nessun thread/polling incoerente dopo STOP/chiusura.

## 9. Esito

- [ ] Casi A–G con esito atteso.
- [ ] Nessun token nei log; nessun CSV corrotto/parziale; header sempre presente.
- [ ] Registrare versione testata, data, ambiente (Windows/XTrader) e note.

> Se un caso fallisce, NON passare alla modalità reale: annota il comportamento,
> apri un'issue e correggi prima di rilasciare.
