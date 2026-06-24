# Design — Mappatura Mercati a frase (FASE 2)

> **Stato: DESIGN / PROPOSTA.** Nessun codice ancora. Questo documento va letto e
> approvato dal proprietario PRIMA dell'implementazione, perché la mappatura mercati
> incide su **CSV → scommessa**: un mercato sbagliato = scommessa sbagliata. Le scelte
> marcate **DA CONFERMARE** aspettano una decisione del proprietario (sono evidenziate
> con una raccomandazione di default).

## 1. Obiettivo

Tradurre una **frase-mercato del provider** nel **Mercato + Selezione XTrader** canonici,
scelti dal **Catalogo XTrader** (gli stessi menù a tendina `Mercato → Selezione` già usati
nel Parser Personalizzato, `parser_builder.market_options()/selection_options()`).

Esempio (richiesto dal proprietario):

```
frase provider:  "goal prima di 70"
⇒  Mercato:   Over/Under 2.5
   Selezione: Over 2.5
```

È un **riconoscimento a frase**: se il messaggio Telegram contiene la frase, il bridge
imposta Mercato+Selezione dal dizionario. Si **richiama dentro il Parser Personalizzato**
(come già il dizionario nomi squadra), così il parser diventa più automatico.

## 2. Dove si colloca (speculare al dizionario nomi)

Il dizionario nomi squadra è già:

- **dati**: `name_mapping_store.py` (funzioni pure + profili in `config.json`);
- **GUI**: area **⚽ Calcio** della scheda **🗺️ Mapping** (`name_mapping_gui.py`);
- **runtime**: `custom_pipeline.build_validated_row()` traduce `EventName` **prima** della
  validazione; se richiesto ma non traducibile → stato **`MAPPING_MISSING`** (fail-closed,
  nessuna riga scritta).

La mappatura mercati replica lo **stesso schema**:

| Livello | Dizionario nomi (esistente) | Dizionario mercati (nuovo) |
|---|---|---|
| Dati/store | `name_mapping_store.py` | **`market_mapping_store.py`** (nuovo) |
| Config key | `name_mapping_profiles` | **`market_mapping_profiles`** (nuovo) |
| GUI | area ⚽ Calcio | area **🎯 Mercati** (già predisposta, vuota) |
| Aggancio parser | `defn.name_mapping_profiles` | **`defn.market_mapping_profiles`** (nuovo) |
| Runtime | traduce `EventName` | imposta `MarketName`/`SelectionName` (+ `MarketType`) |
| Fail-closed | `MAPPING_MISSING` | **`MARKET_MAPPING_MISSING`** (nuovo) |

## 3. Modello dati (proposta)

Una **voce** del dizionario mercati (per-profilo, come i nomi):

```jsonc
{
  "phrase": "goal prima di 70",     // frase del provider (match case-insensitive, vedi §5)
  "market_type": "OVER_UNDER",      // dal catalogo (può servire al contratto CSV)
  "market_name": "Over/Under 2.5",  // dal Catalogo XTrader (market_options)
  "selection_name": "Over 2.5"      // dal Catalogo XTrader (selection_options del mercato)
}
```

Un **profilo mercati** = lista di voci, salvato in `config.json` sotto
`market_mapping_profiles` (stessa forma a profili del dizionario nomi). `market_name`/
`selection_name`/`market_type` **non** sono testo libero: si scelgono dai menù del
Catalogo XTrader, così il valore scritto nel CSV è **sempre** canonico (no typo, no
mercato inesistente).

## 4. Runtime — dove agisce e regola di PRECEDENZA

Hook in `custom_pipeline.build_validated_row()`, **dopo** l'estrazione dei campi dal
messaggio e **prima** della validazione/scrittura, **solo** se il parser ha un profilo
mercati selezionato (`defn.market_mapping_profiles`).

**Regola di precedenza — DA CONFERMARE (raccomandazione di default):**

> Le **regole a colonne del Parser vincono** sul dizionario mercati. Il dizionario
> riempie `MarketName`/`SelectionName`/`MarketType` **solo se** il parser **non** li ha già
> estratti (campo vuoto). Così chi ha già una regola esplicita per il mercato non viene
> mai sovrascritto da un match di frase.

Motivazione: una regola esplicita è un'intenzione precisa dell'utente; il dizionario è un
aiuto "best-effort" per i provider che scrivono i mercati a parole. Evita doppie verità
contrastanti sullo stesso campo.

## 5. Sicurezza / fail-safe (NON negoziabile)

1. **Nessun match ⇒ niente mercato inventato.** Se il profilo mercati è richiesto ma
   nessuna frase combacia, e il mercato non è stato estratto dalle regole → stato
   **`MARKET_MAPPING_MISSING`**: la riga **non** viene scritta nel CSV (come
   `MAPPING_MISSING` per i nomi). Mai scrivere un mercato "a caso".
2. **Match ambiguo (più frasi combaciano) — DA CONFERMARE (default: fail-closed).**
   Se due voci diverse combaciano e indicano Mercato/Selezione **diversi**, è ambiguo →
   `MARKET_MAPPING_MISSING` (non si tira a indovinare). *Alternativa* (se preferisci):
   match della frase **più lunga/più specifica**. Default proposto: **fail-closed**.
3. **Coerenza Mercato↔Selezione.** La selezione deve appartenere al mercato scelto
   (garantito già in fase di GUI: la tendina Selezione dipende dal Mercato). Lo store
   rifiuta voci incoerenti.
4. **Una sola riga attiva.** Invariato: il CSV resta one-signal-at-a-time, svuotato dopo
   il timeout. La mappatura mercati non cambia questa catena.
5. **Match su che testo? — DA CONFERMARE (default: testo grezzo del messaggio).** La frase
   si cerca nel **messaggio originale** (case-insensitive, match di sottostringa su confini
   di parola per evitare falsi positivi). *Alternativa*: su un campo già estratto dal
   parser. Default proposto: **messaggio grezzo**, perché il caso d'uso ("goal prima di 70"
   nel testo libero del canale) non è un campo strutturato.

## 6. GUI (area 🎯 Mercati della scheda Mapping)

Nell'area **🎯 Mercati** (oggi placeholder): selettore profilo (nuovo/rinomina/elimina,
come ⚽ Calcio) + tabella righe:

```
Frase provider           | Mercato (catalogo)   | Selezione (catalogo)  | 🗑
[ goal prima di 70     ] | [ Over/Under 2.5  ▾] | [ Over 2.5         ▾] | ✕
```

Mercato/Selezione = menù dal Catalogo XTrader (Selezione dipende dal Mercato). Nel
**Parser Personalizzato**: una spunta/selettore "profilo mercati" accanto a quello dei
nomi squadra, così al parsing si traducono **sia** i nomi **sia** i mercati.

## 7. Piano di implementazione (PR piccole, una alla volta)

1. **`market_mapping_store.py`** — funzioni pure + `resolve_market(text, profiles)` che
   ritorna `(market_type, market_name, selection_name)` o `None`/ambiguo. **Solo logica +
   test hard** (nessuna GUI, nessun runtime). Tutti i casi di §5 coperti da test.
2. **Aggancio runtime** in `custom_pipeline` con la regola di precedenza §4 e
   `MARKET_MAPPING_MISSING`, + `defn.market_mapping_profiles` nel modello parser. Test hard
   end-to-end (frase → riga CSV corretta; nessun match → niente riga; ambiguo → niente
   riga; regola-colonna vince).
3. **GUI** — area 🎯 Mercati + selettore nel Parser. Verifica manuale su Windows.

Ogni passo: Phase 0, micro-audit, test hard veritieri, una PR, merge manuale.

## 8. Domande aperte (servono decisione del proprietario)

- **D1 — Precedenza** (§4): regola-colonna del parser vince sul dizionario? *(default: sì)*
- **D2 — Ambiguità** (§5.2): match ambiguo ⇒ fail-closed, oppure frase più lunga vince?
  *(default: fail-closed)*
- **D3 — Testo di match** (§5.5): messaggio grezzo, oppure un campo estratto dal parser?
  *(default: messaggio grezzo)*
- **D4 — `MarketType`**: serve mapparlo (oltre a MarketName/SelectionName) per il contratto
  CSV XTrader? *(default: sì, lo prendiamo dal catalogo insieme a Mercato/Selezione)*

Confermando D1–D4 (o accettando i default), parto dal passo 1 (store + test), senza
toccare GUI/runtime finché lo store non è solido.
