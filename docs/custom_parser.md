# Parser Personalizzato — guida (CUSTOM_PARSER_READY)

> Stato: **pronto** (PHASE 3-bis, CP-01…CP-10). Il Parser Personalizzato permette
> di definire dalla GUI *come* estrarre ogni colonna del contratto CSV XTrader da
> un messaggio Telegram, **senza modificare il codice**. Quando è attivo per una
> chat è **autoritativo**. Nel percorso **live** NON c'è fallback al parser hardcoded
> storico (CP-09b): se per la chat non è attivo alcun parser personalizzato il messaggio
> è **ignorato**. Il parser hardcoded P.Bet resta nel repo solo per **compatibilità/test**.

Questo documento descrive il comportamento reale del codice (non promesse): come
si definisce un parser, come vengono estratti e tradotti i valori, quali gate di
sicurezza proteggono il CSV, e dove vengono salvati i parser.

---

## 1. Concetto

Un **Parser Personalizzato** è un insieme di **regole**, una per colonna del CSV.
Ogni regola dice da dove prendere il valore di quella colonna nel messaggio.

Catena completa di un messaggio:

```text
messaggio Telegram
  → estrazione del valore grezzo per regola      (custom_parser_engine, CP-02)
  → trasformazione opzionale                      (transforms, CP-05)
  → value-map opzionale (alias → valore XTrader)  (value_maps, CP-03)
  → riga a 14 colonne + default contratto         (custom_pipeline, CP-04)
  → validazione (modalità + Price + BetType)      (validator, PR-10)
  → instradamento live + gate sicurezza           (signal_router, CP-07/CP-09)
  → scrittura CSV solo se "piazzabile"            (app)
```

Il contratto CSV è la **fonte unica** delle colonne ammesse
(`csv_writer.CSV_HEADER`, 14 colonne):

```text
Provider,EventId,EventName,MarketId,MarketName,MarketType,SelectionId,SelectionName,Handicap,Price,MinPrice,MaxPrice,BetType,Points
```

---

## 2. La regola (`FieldRule`)

| Campo | Significato |
|---|---|
| `target` | colonna CSV di destinazione (deve stare in `CSV_HEADER`) |
| `start_after` | "Inizia dopo": l'estrazione parte **subito dopo** questo testo |
| `end_before` | "Finisce prima": l'estrazione finisce **subito prima** di questo testo (se vuoto → fino a fine riga) |
| `fixed_value` | valore costante: se valorizzato, la colonna vale esattamente questo e l'estrazione dal messaggio è ignorata |
| `transform` | nome di una trasformazione da applicare al valore estratto (es. `score_to_over`) |
| `value_map` | nome di una value-map per tradurre il valore nel valore esatto XTrader |
| `required` | obbligatorio: se il valore finale è vuoto il parser è **"Non pronto"** → nessuna riga CSV |

`fixed_value` e `start_after`/`end_before` sono **alternativi** (non si possono
mettere insieme: `validate_parser_def` lo rifiuta).

### Estrazione: delimitatori tolleranti agli spazi

I delimitatori `start_after`/`end_before` sono testo libero (anche emoji/simboli),
cercati nel messaggio con **tolleranza agli spazi**:

- spazi/tab **ai bordi** del delimitatore vengono ignorati (uno spazio iniziale o
  finale digitato per errore non rompe il match);
- i run di spazi/tab **interni** sono flessibili (uno o più): `"Esito :"` combacia
  con `"Esito :"` e `"Esito  :"`;
- **parole, simboli ed emoji restano letterali**: un delimitatore con parola o
  emoji diversa **non** combacia (`"Quota:"` ≠ `"Quotaz:"`, `📊` ≠ `📈`);
- il valore è preso dal **testo originale** (spazi/accenti **dentro** il valore
  preservati, es. `"Inter v Milan"`), poi rifilato solo ai bordi;
- i **newline non sono toccati**: un delimitatore `"\n"` resta letterale, cioè
  "fino a fine riga"; se manca l'a-capo l'estrazione fallisce (resta "Non pronto").

> Consiglio pratico: nella GUI usa il **test-live**, incolla un messaggio reale e
> verifica subito cosa estrae ogni regola.

### Trasformazioni (`transform`)

Derivano un valore calcolato da quello estratto. Built-in:

- `score_to_over`: punteggio `"6-0"`/`"6:0"`/`"6 x 0"` → `"Over 6,5"` (somma gol +
  linea `,5`). Input non interpretabile → vuoto (→ "Non pronto").

L'ordine è sempre **estrazione → trasformazione → value-map**.

### Value-map (`value_map`)

Traducono il valore grezzo nel valore esatto XTrader. Disponibili:

- `bettype`: `BACK`/`back`/sinonimi → `PUNTA`; `LAY`/`lay`/sinonimi → `BANCA`;
- mappe dal **dizionario** (`data/dizionario_xtrader.csv`): `markettype`,
  `marketname`, `selectionname`, chiavate sia sugli alias interni sia sugli
  **shorthand Telegram** (es. `"GG"` → `Sì`, `"OVER 2.5"` → mercato/selezione
  Over/Under 2,5).

**Sicuro**: value-map sconosciuta o valore non mappato → vuoto (→ "Non pronto"),
mai un lato/selezione tradotto a caso.

### Mappatura nomi squadra (`name_mapping_profiles` + `team_separator`)

Un canale può scrivere le squadre con nomi diversi da quelli che XTrader/Betfair si
aspettano nell'`EventName` (alias, abbreviazioni, lingue diverse). I **profili di
mappatura nomi** (`name_mapping_store`, config `name_mappings`) traducono i nomi
provider nei nomi Betfair/XTrader **prima** della scrittura:

- ogni profilo è una tabella a campi liberi `Betfair/XTrader ↔ Provider` (+ `Country`
  organizzativo); entrambe le colonne le compili tu;
- il parser seleziona uno o più profili (`name_mapping_profiles`) e indica il
  separatore casa/trasferta del canale (`team_separator`, testo libero: `v`, `vs`,
  `-`, `/`; vuoto = default `v`). I separatori **alfabetici** (`v`/`vs`) richiedono
  spazi attorno, così `Liverpool` non viene spezzato sulla `v` interna;
- l'`EventName` viene diviso, casa e trasferta tradotte e ricomposte nel formato
  XTrader `Casa - Trasferta` (`dizionario.compose_event_name`);
- **multi-profilo**: i profili selezionati si applicano nell'ordine dato; in caso di
  conflitto vince la **prima** corrispondenza (deterministico);
- **multi-sport (PR-P10)**: ogni riga di mappatura ha una colonna **Sport** opzionale
  (`Calcio`/`Tennis`/`Basket`/`Rugby Union` o **«(tutti gli sport)»** = agnostica). Se il
  parser ha uno **Sport** impostato, la mappatura considera SOLO le righe di quello sport o
  agnostiche — con **priorità allo sport esatto** sulle agnostiche (un override per-sport
  non viene scavalcato da una riga agnostica salvata prima) — e **salta** le righe taggate
  per un altro sport: così un nome non viene
  tradotto con una voce pensata per uno sport diverso (es. un "Milan" del basket non mappa
  un evento di calcio). Parser senza sport / righe agnostiche → comportamento legacy
  (nessun filtro), retro-compatibile.
- **tipo entità (`entity_type`, #178 §2)**: ogni riga ha anche una colonna **Tipo**
  opzionale con i valori `participant`, `team`, `player`, `competition`, `market`,
  `selection` o **«(qualsiasi tipo)»** = agnostica (chiave di config `entity_type`; vuoto/
  ignoto → agnostica, retro-compatibile con le config salvate prima del campo). Serve a
  dichiarare COSA mappa una riga, così un alias di un altro tipo non scavalca un nome
  squadra; come per lo sport, il **tipo esatto** ha priorità sull'agnostico. **Nel flusso
  live l'`EventName` (i partecipanti dell'evento) è tradotto SOLO dalle righe
  `participant`/`team`/`player` e dalle agnostiche**: le righe `competition`/`market`/
  `selection`, anche con un alias che collide, **non** traducono un partecipante (evita un
  `EventName` CSV sbagliato). Gli altri tipi restano disponibili per la risoluzione quando
  il chiamante li richiede esplicitamente.

**Sicuro (fail-closed)**: se il separatore non si trova **o** una squadra non è nei
profili (per lo sport del parser), lo stato è `MAPPING_MISSING` → **nessuna riga CSV** (un
evento sbagliato = scommessa sbagliata). Nessun nome squadra viene mai tradotto "a caso".
Un parser **senza profili** non applica alcuna mappatura (`EventName` invariato,
retro-compatibile).

**GUI**: i profili si gestiscono nella scheda **Mapping** della finestra «🧰 Strumenti»
(pulsante «🗺️ Mapping» nella finestra principale → `name_mapping_gui.MappingPanel`),
**area ⚽ Calcio** (`NameMappingPanel`): selettore profilo (nuovo/rinomina/elimina) e
tabella `Country | Betfair/XTrader | Provider | Sport | Tipo`. La classe
`NameMappingWindow` resta come finestra standalone (compatibilità). La tabella ha una
colonna **Sport** per riga (PR-P10: «(tutti gli sport)» = agnostica, oppure uno sport
specifico) e una colonna **Tipo** (#178 §2: «(qualsiasi tipo)» = agnostica, oppure
`participant`/`team`/`player`/`competition`/`market`/`selection`). Nel **Parser
Personalizzato** scegli
il **separatore** squadre e spunti i **profili** da usare (checkbox multi-selezione);
«Prova messaggio» risolve i profili dalla config e mostra l'`EventName` tradotto (o
`MAPPING_MISSING` se non mappabile), coerente col runtime.

### Mappatura mercati a frase (`market_mapping_profiles`)

Alcuni canali scrivono il **mercato a parole** dentro il messaggio (es. `Quota 0,5 HT
Prematch`). I **profili di mappatura mercati** (`market_mapping_store`, config
`market_mappings`) leggono il mercato **da una posizione precisa** del messaggio e lo
traducono nel **Mercato + Selezione XTrader** canonici (gli stessi del Catalogo del builder):

- ogni **voce** è `(Inizia dopo, Finisce prima, Testo mercato) → (MarketType, MarketName,
  SelectionName)`. I delimitatori **Inizia dopo / Finisce prima** funzionano **come nel
  Parser** (match tollerante agli spazi; se *Finisce prima* è vuoto → fino a fine riga). Si
  estrae il campo, e se vi compare il **Testo mercato** (case-insensitive, su confini di
  token) la voce scatta. Mercato e selezione **non** sono testo libero: si scelgono dal
  Catalogo XTrader, così il CSV è sempre canonico;
- **perché a delimitatori e non "frase su tutto il messaggio"**: molti provider mettono in
  testa un **banner/menu** con più mercati (es. `P.Bet. 30/0,5HT/1,5HT/1 ASIATICO`); cercare
  la frase nell'intero testo darebbe falsi match/ambiguità. Leggendo **solo** il campo
  delimitato (es. fra `Quota` e `Prematch`) si prende il mercato vero e si ignora il banner.
  Una voce **senza** delimitatori è **preservata** in config (le mappature vecchie non si
  perdono) ma **non applicata** dal bridge finché non aggiungi i delimitatori — la modalità
  "frase su tutto il messaggio" è rimossa, ma senza cancellare dati;
- **precedenza (D1): il dizionario VINCE.** Se una voce combacia in modo univoco, imposta
  `MarketType`/`MarketName`/`SelectionName` **sovrascrivendo** quelli eventualmente estratti
  dalle regole-colonna. Se **nessuna** voce combacia, restano i valori delle regole-colonna.

**Sicuro (fail-closed)**: match **ambiguo** (più voci → mercati diversi nello stesso campo)
→ stato `MARKET_MAPPING_MISSING`, **nessuna riga CSV** (un mercato sbagliato = scommessa
sbagliata). Se nessuna voce combacia **e** le regole-colonna non hanno prodotto un
mercato per la modalità di riconoscimento → ancora `MARKET_MAPPING_MISSING` (mai un
mercato inventato). Una voce con coppia Mercato/Selezione **non nel Catalogo** viene
ignorata (mai scritta); una valida ma non-canonica (case/spazi, `market_type` stantio) è
riportata ai valori canonici del catalogo. Un parser **senza profili mercati** non applica
alcuna mappatura (colonne invariate, retro-compatibile).

La mappatura mercati è **basata sui nomi** (imposta `MarketType`/`MarketName`/
`SelectionName`; il Catalogo non ha gli ID). Per evitare una riga con **identificatori
contraddittori**, quando il dizionario vince la coppia `MarketId`/`SelectionId`
eventualmente estratta dalle regole-colonna viene **azzerata**: il mercato della riga è
univocamente la tupla a nome del dizionario. Conseguenza voluta: un parser in modalità
**ID_ONLY** che usa anche la mappatura mercati a frase, al match, fa **fail-closed** in
validazione (gli ID azzerati mancano) — è una combinazione incoerente e non deve produrre
una scommessa su ID che contraddicono la frase. In **BOTH** la coppia a nome basta, quindi
la riga resta valida senza ID stantii.

**GUI**: l'area **🎯 Mercati** della scheda **Mapping** (`MarketMappingPanel`) è ora
**funzionante**: selettore profilo (nuovo/rinomina/elimina) + tabella `Inizia dopo |
Finisce prima | Testo mercato | Mercato (catalogo ▾) | Selezione (catalogo ▾)`, dove i
delimitatori ritagliano il campo del messaggio, il Testo mercato lo riconosce, e
Mercato/Selezione si scelgono dai menù del Catalogo XTrader (la Selezione dipende dal
Mercato) con `MarketType` derivato dal Catalogo. I profili persistono in `config.json` → `market_mappings`. Rinominare/eliminare un
profilo aggiorna/avvisa i parser che lo selezionano
(`rename_market_mapping_profile_in_files` / `parsers_using_market_mapping_profile`).

Nel **Parser Personalizzato** (`CustomParserPanel`) c'è ora la riga **«Mappatura mercati»**:
un pulsante **«🎯 Dizionario mercati»** (apre `MarketMappingWindow`) e le **checkbox dei
profili mercati** (multi-selezione), accanto a quelle dei nomi squadra. Al salvataggio del
parser i profili spuntati finiscono in `market_mapping_profiles`. Come per i nomi, un profilo
selezionato ma **non più esistente** in config compare come voce **⚠ fantasma** che **blocca
il salvataggio** (e l'anteprima) finché non lo si ricrea o si toglie la spunta — così un
profilo rinominato/eliminato non viene mai riscritto stantio nel parser (niente
`MARKET_MAPPING_MISSING` silenzioso). «Prova messaggio» risolve i profili mercati dalla config
e imposta Mercato/Selezione come il runtime (o fa fail-closed con `MARKET_MAPPING_MISSING`).

---

## 2bis. Modalità di riconoscimento e griglia a 14 colonne

Il builder mostra **tutte e 14 le colonne del contratto già pronte, in ordine fisso**
(una riga per colonna): compili quelle che ti servono e lasci vuote le altre — non si
aggiungono/scelgono colonne a mano, così l'ordine è sempre corretto e non se ne dimentica
nessuna.

La **Modalità** di riconoscimento (`ID_ONLY` / `NAME_ONLY` / `BOTH`) è una proprietà
**del parser** (salvata nel file, campo `mode`; default `NAME_ONLY`). Selezionandola dal
menu, le colonne richieste da quel set diventano **obbligatorie in automatico** (auto
«Obblig.»), senza spuntarle a mano:

| Modalità | Colonne rese obbligatorie |
|---|---|
| `NAME_ONLY` | `EventName`, `MarketType`, `SelectionName` |
| `ID_ONLY` | `MarketId`, `SelectionId` |
| `BOTH` | nessuna forzata (basta **un** set completo: lo decidi tu) |

`Price`, `BetType`, `Provider` non dipendono dalla modalità (la loro obbligatorietà la
gestisci tu). In particolare la casella **«Obblig.» sulla riga `Price`** è l'**unico
comando della quota**: se spuntata il segnale deve avere una quota valida (`>1.0`),
altrimenti è scartato; se non spuntata la quota è opzionale (CSV con `Price` vuoto
ammesso, la quota la mette poi l'azione XTrader). Non esiste più un interruttore globale. A **runtime** la validazione del segnale usa la modalità **del parser**:
ogni parser porta la sua, coerente col builder. **Eccezione (compatibilità):** un parser
salvato *prima* di questa feature non ha il campo `mode` (resta `""`) e in quel caso il
runtime **eredita la modalità globale** `recognition_mode`, così i parser vecchi non
cambiano comportamento. I parser creati/salvati dalla GUI hanno sempre una modalità
esplicita (incl. la voce «(eredita globale)» se la scegli apposta).

### Sport del parser (multi-sport)

Ogni parser può dichiarare uno **Sport** (menu a tendina accanto a «Modalità»): uno fra
**Calcio / Tennis / Basket / Rugby Union**, oppure **«(non specificato)»** = parser
**agnostico**. È salvato nel file del parser (campo `sport`; vuoto = non specificato) ed è
la fonte unica degli sport (`xtrader_bridge/sports.py`), la stessa usata dalla tab Betfair
Sync e dal catalogue client, con la mappa allo `event_type_id` ufficiale Betfair
(Calcio=1, Tennis=2, Basket=7522, Rugby Union=5).

Lo Sport **non cambia le colonne CSV** (restano le 14 generiche): serve a indicare a quale
sport appartiene il segnale così che — nelle versioni successive — la risoluzione degli ID
Betfair (`EventId`/`MarketId`/`SelectionId`) dal dizionario locale possa restringersi
all'`event_type_id` corretto. Uno Sport non riconosciuto (file manomesso) **blocca** la
validazione invece di scegliere un event_type_id a caso; un parser salvato *prima* di questa
feature non ha il campo `sport` e resta **agnostico** (retro-compatibile). Poiché il parser
attivo è per profilo (`active_parser`/`parser_by_chat` nello snapshot del profilo), cambiando
profilo cambia anche lo Sport del parser usato.

### Anagrafica Provider

La colonna **`Provider`** si compila da un **menu a tendina** con i nomi provider salvati
(invece di digitarli ogni volta): così eviti errori di battitura — il Provider deve
combaciare col filtro Provider dell'azione XTrader — e riusi gli stessi nomi su più
parser. Il pulsante **«➕ Provider»** aggiunge un nuovo nome all'anagrafica (salvato in
`config.json` sotto `providers`, condiviso fra tutti i parser). Un valore Provider già
presente nel parser ma non (più) in anagrafica resta selezionato e non si perde.

Per una gestione completa dell'anagrafica c'è il pulsante **«📇 Provider»** nella GUI
principale: apre una finestra dedicata dove **vedere**, **aggiungere** e **rimuovere** i
nomi provider salvati, senza dover aprire il builder. Le modifiche persistono subito in
`config.json` (chiave `providers`) e si riflettono nelle tendine della colonna Provider.

---

## 3. Gate di sicurezza (perché non scrive righe sbagliate)

Tutti questi gate devono passare perché una riga venga scritta:

1. **"Non pronto"** (obbligatori): se un campo `required` è vuoto dopo
   estrazione/trasformazione/value-map → nessuna riga CSV.
2. **Validazione contratto**: `Price` deve essere numerico `> 1.0`,
   `BetType ∈ {PUNTA, BANCA}`, e i campi richiesti dalla modalità di
   riconoscimento (`ID_ONLY`/`NAME_ONLY`/`BOTH`) devono esserci. Il separatore
   decimale di `Price`/`MinPrice`/`MaxPrice` è normalizzato a `.` (es. `1,85`→`1.85`;
   `1.234,56`→`1234.56` con raggruppamento migliaia valido). Un doppio separatore
   **malformato** (es. `1.2,3`) NON viene aggiustato: resta invalido → `INVALID_PRICE`
   (fail-closed, niente prezzo sbagliato nel CSV).
3. **Gate di contenuto**: un parser i cui obbligatori sono **tutti `fixed_value`**
   sarebbe "piazzabile" su qualsiasi testo (anche vuoto). Nel live, che bypassa il
   prefiltro marker per i parser custom attivi, questo scriverebbe lo stesso bet
   su ogni messaggio. Perciò una riga è accettata solo se **almeno una regola di
   estrazione che rappresenta contenuto di segnale** (non `fixed_value`) ha trovato un
   valore nel messaggio: una regola **obbligatoria** (`required`) **oppure** una regola su
   un **campo di riconoscimento rilevante per la modalità** (in `NAME_ONLY` i campi nome,
   in `ID_ONLY` i campi ID, in `BOTH` entrambi i set) — stato `NO_CONTENT_MATCH`
   altrimenti. Un'estrazione **opzionale** "larga" su un campo **non** di riconoscimento
   (es. una nota) non basta: non deve far passare un messaggio non-segnale che la attiva
   per caso (A10). Per usare un campo non di riconoscimento come "trigger" di contenuto,
   marcalo **obbligatorio**.
4. **Approvazione chat**: un parser è usato solo per la chat **configurata**
   (`chat_id`) o per le chat con voce esplicita in `parser_by_chat`. Un
   `active_parser` globale **non** fa scommettere chat non approvate.
5. **Autoritativo, niente doppio parsing**: quando un parser custom è attivo per
   la chat, se non produce una riga piazzabile il segnale è **scartato** — non si
   ripiega sul parser hardcoded (che potrebbe interpretare diversamente lo stesso
   messaggio).

---

## 3bis. Diagnostica «Prova messaggio» (perché "Non pronto")

Nel builder, **«Prova messaggio»** non dà più solo il verdetto: mostra una
**diagnostica per ogni colonna** lungo la catena
`estrazione → trasformazione → value-map → validazione`, così si capisce *quale*
campo ha fallito e *perché*. Il pulsante **«📋 Copia diagnostica»** copia il report
negli appunti (utile per condividerlo).

Per ogni colonna il report mostra il valore `grezzo` estratto, `→tr` (dopo
trasformazione) e `→map` (dopo value-map), più un codice di stato:

| Codice | Significato |
|---|---|
| `OK` / `EMPTY_OPTIONAL` | valore valido / vuoto ma facoltativo (non blocca) |
| `START_NOT_FOUND` | il delimitatore «Inizia dopo» non è nel messaggio |
| `END_NOT_FOUND` | «Finisce prima» non trovato dopo l'inizio |
| `REQUIRED_EMPTY` | campo obbligatorio rimasto vuoto |
| `TRANSFORM_FAILED` | la trasformazione non ha prodotto un valore |
| `VALUE_MAP_MISS` | la value-map non ha trovato il valore (→ vuoto) |
| `INVALID_PRICE` | `Price` non numerico o ≤ 1.0 |
| `INVALID_BETTYPE` | `BetType` non è `PUNTA`/`BANCA` |
| `MODE_REQUIRED_MISSING` | campo richiesto dalla Modalità di riconoscimento mancante |
| `NO_CONTENT_MATCH` (messaggio) | nessuna estrazione ha trovato nulla: solo valori fissi / nessun match |

Il verdetto della diagnostica **coincide** con ciò che il bridge scriverebbe a
runtime (stessa pipeline `build_validated_row`): se "Prova messaggio" dice pronto,
il live scrive; se dice "Non pronto", il live scarta — col motivo per colonna.

---

## 4. Quale parser è attivo (routing)

Risoluzione (in `parser_manager` / `signal_router`):

1. se la chat di origine ha una voce in `parser_by_chat` → quel parser;
2. altrimenti, se è la chat configurata (`chat_id`) e c'è un `active_parser`
   globale → quel parser;
3. altrimenti → **nessun parser**: nel live il messaggio è **ignorato** (`NO_PARSER`,
   CP-09b); il parser hardcoded **non** entra in gioco (resta solo per compatibilità/test).

Nel live, il chat id usato è quello **reale del messaggio** (così l'override
per-chat funziona anche con setup multi-chat dove `chat_id` singolo non è
impostato). Se né `chat_id` né `parser_by_chat` sono configurati, vale il
comportamento legacy (tutte le chat ammesse — responsabilità dell'utente).

---

## 5. Persistenza, import/export

- I parser sono salvati **per-parser** in una **cartella utente persistente**:
  `custom_parser.default_parsers_dir()` → `<config_dir>/parsers/<nome>.json`,
  cioè `config_store.config_dir()/parsers`. Su Windows è
  `%APPDATA%\XTraderBridge\parsers`; in dev/Linux/macOS è
  `~/.config/XTraderBridge/parsers` (o `$XDG_CONFIG_HOME/XTraderBridge/parsers`).
  È questa la cartella da editare/backuppare per l'app reale (i test passano
  invece una `dir_path` temporanea esplicita). La scelta della cartella utente
  fa sopravvivere i parser a reinstallazioni/spostamenti dell'EXE.
- Nota: `.gitignore` esclude anche `data/parsers/` (voce difensiva, sono
  configurazione utente e non si committano), ma **non** è il percorso usato a
  runtime: quello di default è `<config_dir>/parsers/` qui sopra.
- Scrittura **atomica** e rifiuto di nomi che collidono o non fanno round-trip col
  filename (anti path-traversal).
- `parser_io.export_parser` / `import_parser` per condividere i file (valida prima
  di scrivere/salvare; import non sovrascrive senza `overwrite=True`).
- `parser_io.example_parser()` + `fixture_message()`: un parser realistico
  (Match/Esito/Quota/Lato) che produce una riga piazzabile end-to-end, usato anche
  nei test.
- **Gestione dalla finestra builder (CP-11):** la tendina "Parser salvati" elenca i
  parser nella cartella utente, con **🆕 Nuovo / 📂 Carica / 📑 Duplica / 🗑 Elimina**.
  La duplica chiede un nuovo nome e **rifiuta** un nome già esistente (non
  sovrascrive); l'eliminazione rimuove il file per nome (anti path-traversal). Un
  file corrotto compare in lista col nome del file, senza nascondere gli altri.
  L'**attivazione** resta nella finestra "📡 Chat sorgenti" (parser globale o
  per-chat); la finestra builder serve a creare/modificare/gestire le definizioni.
- **Adattamento allo schermo:** la finestra builder è interamente **scrollabile**
  (un solo contenitore: griglia 14 colonne, area "Prova messaggio" e tabella
  diagnostica restano raggiungibili anche su schermi piccoli). Come tutte le finestre
  del bridge, si apre con altezza **clampata all'area schermo** e un `minsize`, tramite
  l'helper condiviso `gui_utils.fit_to_screen(...)`, così non sfora sotto la taskbar.

---

## 5-bis. Output multi-riga: MultiMarket / MultiSelection (#192)

Un singolo messaggio Telegram può generare **più righe CSV**. Le **14 righe del parser**
restano la **riga base** (campi comuni: Provider, EventName, eventuali Market/Selection di
default, Price, BetType…); due opzioni del modello la espandono in più righe:

- **MultiMarket** (`multi_market_enabled` + `multi_markets`): più **mercati diversi** della
  stessa partita (es. `FIRST_HALF_GOALS_05 / Over 0,5` **e** `OVER_UNDER_15 / Over 1,5`).
- **MultiSelection** (`multi_selection_enabled` + `multi_selections`): più **selezioni dello
  stesso mercato** (es. `CORRECT_SCORE` con `1 - 0`, `2 - 1`, `1 - 2`).

**Modello** (`custom_parser.MultiRowRule`): ogni riga multi porta
`start_after, end_before, market_type, market_name, selection_name, price, min_price,
max_price, bet_type, points, handicap, enabled`. Ogni campo **non vuoto SOVRASCRIVE** quello
della riga base; un campo **vuoto eredita** dalla base. Tutto è serializzato nel JSON del
parser ed è **retro-compatibile**: i file salvati prima di #192 (senza questi campi) caricano
con flag `False` e liste vuote → comportamento **single-row identico a prima**.

**Pipeline** (`custom_pipeline.build_validated_rows`): ritorna una **lista** di righe validate
(una per mercato/selezione attiva). Ogni riga è validata singolarmente: una riga non valida
**non blocca** le altre (l'instradamento scrive solo quelle piazzabili). `signal_router.
resolve_row` espone le righe in `RouteResult.rows` (e `RouteResult.row` resta la **prima**,
retro-compatibile).

**Regole e limiti (v1):**

- `BetType` resta `PUNTA`/`BANCA` (contratto XTrader): una riga multi con un valore diverso
  (es. `BACK`) risulta **non valida** in validazione — il contratto CSV non cambia.
- `start_after`/`end_before` delle righe multi sono **conservati** ma in questa versione i
  valori sono **fissi** (override diretto); l'estrazione per-riga è un'estensione futura.
- **MultiMarket + MultiSelection insieme** generano righe **separate** (prima i mercati, poi
  le selezioni sul mercato base), **mai** il prodotto cartesiano (`custom_pipeline.
  both_multi_active` segnala il caso, da avvisare in GUI).
- **Deduplica per-riga** (`signal_dedupe.row_dedup_key`): la chiave combina l'hash del
  messaggio con `Provider+EventName+MarketType+SelectionName+BetType`, così righe diverse
  dello **stesso** messaggio non si auto-dedupano, ma una riga **identica** reinviata resta un
  duplicato.
- **Coda/CSV**: `write_path.commit_signals` valuta ogni riga (dedup per-riga + limiti), accoda
  le righe `WRITE` e riscrive il CSV in modo **atomico** (rollback completo se la scrittura
  fallisce). Garanzie allineate al single-row: in **DRY_RUN** non scrive nulla; se **tutte** le
  righe sono soppresse (duplicati/limiti) il CSV **non viene riscritto** (XTrader non riconsuma
  righe identiche); una riga `DAILY_LIMITED` o oltre il tetto `max_active` **non** è scritta e il
  suo consumo dedup/daily è **annullato** (ritentabile).
  - In `APPEND_ACTIVE`/`QUEUE_UNTIL_CONFIRMED` configurare **`max_active` ≥ numero di righe** del
    messaggio (le righe oltre il tetto sono bloccate, non scritte).
  - In `OVERWRITE_LAST` l'«ultima istruzione» è il **blocco intero** del messaggio: tutte le
    righe generate restano attive insieme (sostituiscono il blocco precedente), via
    `signal_queue.replace_block`.
- **ID coerenti**: quando una riga multi cambia `MarketType`/`MarketName`/`SelectionName`/
  `Handicap`, gli eventuali `MarketId`/`SelectionId` ereditati dalla base vengono **azzerati**
  (una riga non può nominare un mercato e identificarne un altro per ID).

**GUI (scheda 🧩 Parser di «🧰 Strumenti»):** la sezione **«Output multi-riga»** sopra la griglia
14 colonne offre due interruttori indipendenti — **MultiMarket** e **MultiSelection** — ciascuno
con un pulsante **`➕ Aggiungi`** che inserisce una **riga dinamica** editabile (Tipo mercato,
Mercato, Selezione, Quota, BetType, Handicap) con casella **Attiva** e pulsante **`🗑 Rimuovi`**.
Un **banner ⚠** avvisa quando entrambi gli interruttori sono attivi (righe **separate**, non
cartesiane) o quando un interruttore è acceso senza righe abilitate. **«Prova messaggio»** mostra,
oltre al verdetto della riga base, una **tabella «Anteprima righe generate»** con **una riga per
ogni riga CSV** che il messaggio produrrebbe (Base / Mercato / Selezione), col **verdetto
per-riga** (✅ piazzabile · ⛔ + motivo): usa lo **stesso motore del runtime**
(`build_validated_rows`), quindi non mente.

La logica che la GUI usa (round-trip dei campi multi in `to_def()`, gestione righe, avvisi,
anteprima `ParserBuilder.preview_rows`) vive nel **controller** ed è coperta in CI da
`tests/unit/test_parser_builder_multirow.py`; i widget (`custom_parser_gui.py`) restano una
**vista sottile**, verificabile solo manualmente su Windows (display richiesto). Il motore è
coperto da `tests/unit/test_multirow_192.py`.

**Collaudo manuale GUI (Windows):** apri «🧰 Strumenti» → scheda 🧩 Parser; spunta MultiMarket,
premi `➕ Aggiungi mercato` due volte e compila due mercati; incolla un messaggio reale e premi
«Prova messaggio»; verifica che la tabella mostri **2 righe Mercato** entrambe ✅. Spunta anche
MultiSelection, aggiungi 3 selezioni → la tabella deve mostrare **5 righe** (2 Mercato + 3
Selezione), col banner ⚠ «righe SEPARATE». Salva, riapri il parser e verifica che interruttori
e righe siano ripristinati.

## 6. Riferimenti (codice e test)

| Componente | Modulo | Test |
|---|---|---|
| Modello dati + persistenza | `custom_parser.py` | `tests/unit/test_custom_parser_model.py` |
| Motore di estrazione (delimitatori tolleranti) | `custom_parser_engine.py` | `tests/unit/test_custom_parser_engine.py` |
| Value-map (bettype + dizionario) | `value_maps.py` | `tests/unit/test_value_maps.py` |
| Mappatura nomi squadra (profili) | `name_mapping_store.py` | `tests/unit/test_name_mapping.py` |
| GUI Mapping nomi — area ⚽ Calcio (+ 🎯 Mercati predisposta) | `name_mapping_gui.py` (`MappingPanel`, `NameMappingPanel`) | verifica manuale (GUI) |
| Trasformazioni | `transforms.py` | `tests/unit/test_transforms.py` |
| Riga validata col contratto | `custom_pipeline.py` | `tests/unit/test_custom_pipeline.py` |
| Diagnostica «Prova messaggio» (per-campo) | `parser_diagnostics.py` | `tests/unit/test_parser_diagnostics.py` |
| Builder GUI (controller + vista) — scheda 🧩 Parser di "🧰 Strumenti" | `parser_builder.py`, `custom_parser_gui.py` (`CustomParserPanel`) | `tests/unit/test_parser_builder.py` |
| Output multi-riga GUI (controller: round-trip, righe, anteprima `preview_rows`) | `parser_builder.py` (`PreviewRow`, `preview_rows`, `multi_warnings`), `custom_parser_gui.py` (sezione «Output multi-riga» + tabella anteprima) | `tests/unit/test_parser_builder_multirow.py` (+ vista: verifica manuale GUI) |
| Adattamento finestre allo schermo (clamp altezza + minsize) | `gui_utils.py` | `tests/smoke/test_imports.py` |
| Finestra hub "🧰 Strumenti" a schede (consolidazione GUI) | `tools_gui.py` | `tests/smoke/test_imports.py` |
| Parser attivo / override per chat | `parser_manager.py` | `tests/unit/test_parser_manager.py` |
| Import/export + esempio | `parser_io.py` | `tests/unit/test_parser_io.py` |
| Instradamento live + gate | `signal_router.py` | `tests/unit/test_signal_router.py` |
| **Catena end-to-end** | — | `tests/integration/test_custom_parser_end_to_end.py` |

> Note di verifica: la **GUI** del builder e il **flusso live** Telegram→CSV vanno
> provati a mano su Windows (non testabili in ambiente headless). Tutta la logica
> di parsing/validazione/instradamento è invece coperta da test automatici. Il
> merge di ogni PR resta **manuale** del proprietario.
