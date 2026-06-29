"""Parsing dei messaggi Telegram P.Bet. (nessuna dipendenza dalla GUI).

PR-09: parser robusto che gestisce messaggi con emoji **e** in testo semplice.
Estrae signal_type, squadre (normalizzate "Home v Away" da v/vs/-), quota
(virgola o punto), score, minuto, probabilità, bet_type (BACK/LAY) e flag live.
NON inventa dati: i campi non presenti restano vuoti (il blocco dei segnali
incompleti — incl. quota mancante — è di recognition/validazione, PR-10).
"""

import re

from . import numbers_re

_HAS_ALPHA = re.compile(r'[A-Za-zÀ-ÿ]')
_EMOJI_MARKERS = ('🏆', '🆚', '⚽', '⌚', '📊', '📈')

# Numero ben formato (no "1.2.3"): intero con al più una parte decimale. Frammento
# condiviso (anti-drift, audit L4).
_NUM = numbers_re.DECIMAL

# "Quota X"/"@X" con marker HT/FT **adiacente** al numero (audit B2): cattura il numero.
# Pattern UNICO condiviso da `_extract_quota` (presenza → modalità linea) e
# `_extract_ft_line_quota` (recupero quota a fine tempo), così la logica non diverge.
_QUOTA_HTFT_ADJ = re.compile(r'(?:quota|@)[:\s]*(' + _NUM + r')\s*(?:ht|ft)\b', re.IGNORECASE)

# Separatori squadre: " v "/" vs " (forti) preferiti a " - " (debole, ambiguo).
_SEP_VVS = re.compile(r'^(.+?)\s+(?:vs|v)\s+(.+)$', re.IGNORECASE)
_SEP_DASH = re.compile(r'^(.+?)\s+-\s+(.+)$')

# Parole-etichetta (match per TOKEN intero, non startswith: così "Preston" ≠ "pre").
_LABEL_WORDS = frozenset({
    'quota', '@', 'time', 'tempo', 'minuto', 'score', 'risultato', 'prob',
    'probabilità', 'probabilita', 'probability', 'lega', 'campionato',
    'competition', 'live', 'pre', 'prematch', 'punta', 'banca', 'back', 'lay',
})

# Coda con punteggio/tempo da rimuovere prima di leggere le squadre
# (es. "Silver Stars FC 6 - 0 46m" → "Silver Stars FC").
# La classe [-–:] include di proposito sia il trattino ASCII "-" sia l'EN DASH "–"
# (e i due punti) perché i punteggi reali usano l'uno o l'altro carattere.
_SCORE_TAIL = re.compile(r'\s+\d+\s*[-–:]\s*\d+(?:\s.*)?$')
# Punteggio che fa da SEPARATORE tra due squadre su una riga 🆚 ("Real Madrid 2 - 1 Barcelona"):
# cattura home (prima del punteggio) e away (dopo). Diverso da _SCORE_TAIL, che rimuove un
# punteggio a FINE riga (e divorerebbe la squadra away di una riga con score in mezzo, #184 M10).
_SCORE_SEP = re.compile(r'^(.+?)\s+\d+\s*[-–:]\s*\d+\s+(.+)$')
# Token di metadati "non-squadra" che possono SEGUIRE (o COSTITUIRE) un lato in una riga 🆚 con
# punteggio-separatore: minuti col marcatore (46m, 46', 90+2) e stati (HT/FT/LIVE/PRE/PREMATCH).
# NB: una cifra NUDA (es. "04" in "Schalke 04", "1860" in "1860 Munich") NON è metadato — fa parte
# del nome — quindi è esclusa: si distingue per il marcatore esplicito (m/'/+) o per essere una
# parola di stato. Così si recuperano i club a cifra iniziale e si scartano i suffissi di tempo/stato
# (#184 M10, Codex P1/P2).
_META_TOK = r"(?:\d+\s*[m'’]|\d+\+\d+|ht|ft|live|prematch|pre)"
# Coda di uno o più token di metadati a fine lato ("Barcelona 46m FT" → "Barcelona").
_META_TAIL = re.compile(r'(?:\s+' + _META_TOK + r')+\s*$', re.IGNORECASE)
# L'intero lato è SOLO un token di metadati (nessuna squadra): "46m", "HT", "FT", "LIVE".
_META_ONLY = re.compile(r'^' + _META_TOK + r'$', re.IGNORECASE)
# Token di stato da togliere dal signal_type (LIVE/PRE) prima del mapping.
_STATUS_TAIL = re.compile(r'\s+\b(?:live|pre|prematch)\b.*$', re.IGNORECASE)


def _is_odds(value: str) -> bool:
    """Una quota decimale offerta è sempre **> 1.0**: così "0,5" (linea del mercato,
    es. "Quota 0,5 HT") non viene scambiato per una quota, e nemmeno "1,00" (che a
    quota piena non dà guadagno e non è un prezzo piazzabile)."""
    try:
        return float(value) > 1.0
    except (TypeError, ValueError):
        return False


def _is_half_line(value: str) -> bool:
    """True se `value` è una linea over/under a mezzo punto (X.5: 0.5, 1.5, 2.5…),
    convenzione universale con cui i mercati esprimono le linee. Serve a distinguere,
    in "Quota X HT/FT" SENZA "Prematch:", una LINEA (X.5 → da ignorare) da una QUOTA
    (qualsiasi altro valore → la quota offerta, A3). Indipendente dal layout del
    messaggio: guarda solo il valore."""
    try:
        f = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return False
    return abs((f % 1.0) - 0.5) < 1e-9


def _extract_quota(line: str):
    """Quota reale da una riga.

    Nel formato P.Bet "Quota X,Y HT/FT Prematch:Z" il numero X,Y è la **linea** del
    mercato (non una quota): la quota offerta è il valore dopo "Prematch:". Questa forma
    è riconosciuta da un marker di linea — `HT`/`FT` oppure `Prematch:` — così non si
    scambia la linea per il prezzo. Il recupero della quota quando "Quota X HT/FT" non ha
    alcun `Prematch:` nell'intero messaggio (A3) è gestito a parte da
    `_extract_ft_line_quota` in `parse_message`, che vede tutte le righe.
    Altrove è "Quota X" / "@X". Solo quote valide: > 1, ben delimitate (no "1.2.3").
    Il boundary `(?!\\d|[.,]\\d)` rifiuta sia una cifra successiva sia un separatore
    decimale seguito da cifra — così "1.85.3"/"1,85,3" non vengono troncati a un
    prefisso ("1.8") — ma ammette la punteggiatura finale di frase ("Quota 1,85." → 1.85).
    """
    low = line.lower()
    # Modalità "linea" (il numero dopo Quota è la LINEA del mercato, la quota vera è dopo
    # "Prematch:"): si attiva SOLO se il marker HT/FT è **adiacente** al numero dopo Quota
    # (audit B2) oppure se c'è un "Prematch:". Prima si cercava `\b(?:ht|ft)\b` sull'INTERA
    # riga: due token di 2 lettere comunissimi vaganti altrove ribaltavano la modalità e
    # facevano perdere/promuovere male la quota.
    line_marker = bool(_QUOTA_HTFT_ADJ.search(line)) or bool(re.search(r'prematch\s*:', low))
    if line_marker:
        m = re.search(r'prematch[:\s]*(' + _NUM + r')(?!\d|[.,]\d)', line, re.IGNORECASE)
    else:
        m = re.search(r'(?:quota|@)[:\s]*(' + _NUM + r')(?!\d|[.,]\d)', line, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).replace(',', '.')
    return val if _is_odds(val) else None


def _extract_ft_line_quota(line: str):
    """Recupero A3: su una riga "Quota X HT/FT" il numero X è una LINEA over/under solo
    se è un valore `.5` (`_is_half_line`: 0.5/1.5/2.5…); altrimenti è la **quota** offerta
    (es. "Quota 1,90 FT" → 1.90) e non va persa.

    Va usato SOLO come fallback whole-message (vedi `parse_message`): si applica quando in
    TUTTO il messaggio non c'è alcun `Prematch:`. Se un `Prematch:` esiste (anche su una
    riga diversa, o malformato) la quota vera è lì e non si promuove la linea a prezzo —
    nel dubbio si fallisce chiusi. Residuo noto: una quota esattamente `.5` (es. 1,50) è
    indistinguibile da una linea e resta persa (fail-safe: meglio persa che sbagliata)."""
    # Il marker HT/FT dev'essere ADIACENTE al numero dopo Quota (audit B2), non un token
    # vagante altrove sulla riga: solo così "Quota X HT/FT" identifica davvero una linea/quota
    # a fine tempo. Il numero X è una LINEA se .5 (ignorato), altrimenti è la quota offerta.
    m = _QUOTA_HTFT_ADJ.search(line)
    if m is None or _is_half_line(m.group(1)):
        return None
    val = m.group(1).replace(',', '.')
    return val if _is_odds(val) else None


def _extract_probability(line: str):
    """Probabilità da "...X%" (numero ben formato e ben delimitato).

    Il lookbehind `(?<![\\d.,])` evita di prendere un frammento di un token
    malformato: "1.2.3%" non deve dare "2.3" — viene rifiutato (None).
    """
    m = re.search(r'(?<![\d.,])(' + _NUM + r')\s*%', line)
    return m.group(1) if m else None


def _looks_like_label(line: str) -> bool:
    """True se la riga è un'etichetta (Quota/Score/Time/...) e non una coppia di
    squadre: confronto per TOKEN intero (così "Preston" ≠ "pre")."""
    low = line.lower()
    if 'p.bet' in low:
        return True
    first = low.split(' ', 1)[0]
    if ':' in first:                       # "Score:", "Time:", "Quota:" ...
        return True
    return first.rstrip(':.') in _LABEL_WORDS


def _teams_from(line: str, sep: re.Pattern):
    """Se la riga (ripulita dalla coda punteggio) è una coppia di squadre con
    il separatore dato e lettere su entrambi i lati, ritorna "Home v Away"."""
    if _looks_like_label(line) or any(e in line for e in _EMOJI_MARKERS):
        return None
    cleaned = _SCORE_TAIL.sub('', line).strip()
    # togli un'eventuale coda quota/@/probabilità sulla stessa riga, così non finisce
    # nell'EventName: "Inter v Milan Quota 1,85" / "... @ 1,85" / "... Probabilità 72%".
    # NB: "@" senza "\b" per coprire anche la forma spaziata "@ 1,85"; coperte sia le
    # etichette inglesi (probability/prob) sia quelle italiane (probabilità/probabilita).
    cleaned = re.sub(r'\s+(?:quota\b|@|probabilit[àa]\b|probability\b|prob\b).*$', '',
                     cleaned, flags=re.IGNORECASE).strip()
    m = sep.match(cleaned)
    if m and _HAS_ALPHA.search(m.group(1)) and _HAS_ALPHA.search(m.group(2)):
        return f"{m.group(1).strip()} v {m.group(2).strip()}"
    return None


def _clean_team_side(side: str):
    """Ripulisce un lato squadra (di una riga 🆚 con punteggio-separatore) dalla coda di metadati
    di tempo/stato (`Barcelona 46m` → `Barcelona`) e lo valida. Ritorna il nome pulito, oppure
    `None` se NON è una squadra reale: vuoto, solo metadati (`46m`/`HT`/`FT`/`LIVE`) o senza
    lettere. Una cifra iniziale è ammessa (`1. FC Köln`, `1860 Munich`): non è metadato (#184 M10,
    Codex P1/P2)."""
    s = _META_TAIL.sub('', side).strip()
    if not s or _META_ONLY.match(s) or not _HAS_ALPHA.search(s):
        return None
    return s


def _teams_from_score(line: str):
    """Fallback per le righe 🆚 dove il PUNTEGGIO fa da separatore tra le squadre
    ("Real Madrid 2 - 1 Barcelona" → "Real Madrid v Barcelona"): senza, `_SCORE_TAIL`
    rimuoverebbe il punteggio E la squadra in trasferta, perdendo il segnale (#184 M10).

    Si applica SOLO alle righe 🆚 (l'emoji conferma che è una coppia di squadre), MAI al testo
    libero, dove uno score in mezzo è troppo ambiguo ("Italy 2 - 1 Serie A"). Ogni lato è ripulito
    dalla coda di metadati (minuto/stato) e validato come squadra reale da `_clean_team_side`: così
    "Real Madrid 2 - 1 Barcelona 46m" → "Real Madrid v Barcelona", mentre "... 2 - 1 HT/FT/LIVE" o
    "46m 2 - 1 ..." falliscono chiusi (nessuna squadra), e i club a cifra iniziale sono ammessi."""
    if _looks_like_label(line) or any(e in line for e in _EMOJI_MARKERS):
        return None
    # togli un'eventuale coda quota/@/probabilità sulla stessa riga (come in `_teams_from`).
    cleaned = re.sub(r'\s+(?:quota\b|@|probabilit[àa]\b|probability\b|prob\b).*$', '',
                     line, flags=re.IGNORECASE).strip()
    m = _SCORE_SEP.match(cleaned)
    if not m:
        return None
    home = _clean_team_side(m.group(1))
    away = _clean_team_side(m.group(2))
    if not home or not away:
        return None
    return f"{home} v {away}"


def _find_teams(lines) -> str:
    """Cerca la riga squadre in testo semplice: SOLO " v "/" vs " (cue forte).
    Il separatore " - " è ammesso solo nelle righe 🆚 (l'emoji conferma le squadre):
    in testo libero è troppo ambiguo (competizioni come "Italy - Serie A", punteggi)."""
    for raw in lines:
        t = _teams_from(raw.strip(), _SEP_VVS)
        if t:
            return t
    return ""


def parse_message(text: str) -> dict:
    """Estrae i campi da un messaggio P.Bet. (emoji o testo)."""
    text = text or ""
    lines = text.strip().split('\n')
    result = {
        'signal_type': '',
        'competition': '',
        'teams': '',
        'score': '',
        'time_': '',
        'quota': '',
        'probability': '',
        'bet_type': 'BACK',
        'live': False,
    }

    if re.search(r'\blive\b', text.lower()):
        result['live'] = True

    # bet_type SOLO da una riga-lato dedicata che contiene ESATTAMENTE un token
    # "Punta"/"Banca"/"Back"/"Lay" (una sola parola), NON da testo libero: così
    # né "Lay Town" (squadra) né "Lay Cup"/"Banca League" (lega/nota) forzano il
    # lato sbagliato (BANCA). Default: BACK.
    # Classe LETTERE Unicode `[^\W\d_]` invece di `[a-zàèéìòù]` (audit L5): la classe
    # ristretta SPEZZAVA una parola-lato con un accento non elencato (es. "Bancä") in più
    # token → len!=1 → riga saltata → bet_type restava al default BACK anche per un segnale
    # LAY (lato OPPOSTO, safety-critical). Le lettere Unicode coprono tutti gli accenti.
    for raw in lines:
        toks = re.findall(r'[^\W\d_]+', raw.lower())
        if len(toks) != 1:
            continue
        if toks[0] in ('banca', 'lay'):
            result['bet_type'] = 'LAY'
            break
        if toks[0] in ('punta', 'back'):
            result['bet_type'] = 'BACK'
            break

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if 'P.Bet.' in line:
            m = re.search(r'P\.Bet\.\s+(.+?)(?:\s+[🔊✅🔇]|$)', line)
            if m:
                # togli i token di stato (LIVE/PRE) così resta l'alias puro per il mapping.
                result['signal_type'] = _STATUS_TAIL.sub('', m.group(1).strip()).strip()
            continue
        if '🏆' in line:
            result['competition'] = re.sub(r'[🏆\s]+', ' ', line).strip()
            continue
        if '🆚' in line:
            base = re.sub(r'[🆚]', ' ', line).strip()
            # v/vs (forte) → " - " (debole, ammesso perché l'emoji conferma) → punteggio come
            # separatore ("Real Madrid 2 - 1 Barcelona", #184 M10) come ultimo fallback.
            t = _teams_from(base, _SEP_VVS) \
                or _teams_from(base, _SEP_DASH) \
                or _teams_from_score(base)
            result['teams'] = t or result['teams']
            continue
        if '⚽' in line:
            result['score'] = re.sub(r'[⚽\s]+', ' ', line).strip()
            continue
        if '⌚' in line:
            result['time_'] = re.sub(r'[⌚\s]+', ' ', line).strip()
            continue
        if '📊' in line or '📈' in line:
            # Riga mista (es. "📈Quota 1,85 📊72%"): estrai sia probabilità sia quota,
            # non fermarti alla prima trovata.
            prob = _extract_probability(line)
            if prob and not result['probability']:
                result['probability'] = prob
            if not result['quota']:
                # Quota SOLO da marker espliciti (Quota/@ o HT/FT-Prematch): niente
                # numero "nudo" inventato (un "📈 1.2.3" non deve produrre un prezzo).
                # Anche su riga con sola 📊 ("📊72% Quota 1,85") la quota testo va presa.
                q = _extract_quota(line)
                if q:
                    result['quota'] = q
            continue

        # ── righe in testo semplice (senza emoji) ──
        q = _extract_quota(line)
        if q and not result['quota']:
            result['quota'] = q
            continue
        ms = re.search(r'(?:score|risultato)[:\s]+(.+)$', line, re.IGNORECASE)
        if ms:
            result['score'] = ms.group(1).strip()
            continue
        mt = re.search(r'(?:time|tempo|minuto)[:\s]+(.+)$', line, re.IGNORECASE)
        if mt:
            result['time_'] = mt.group(1).strip()
            continue
        prob = _extract_probability(line)
        if prob and not result['probability']:
            result['probability'] = prob
            continue

    # A3: quota su riga "Quota X HT/FT" quando l'INTERO messaggio non ha alcun
    # "Prematch:". Solo allora X (se non è una linea .5) è la quota: se un "Prematch:"
    # esiste — anche su un'altra riga o malformato — la quota vera è lì e non si promuove
    # la linea a prezzo (fail-closed). Eseguito dopo il loop per vedere tutte le righe.
    if not result['quota'] and not re.search(r'prematch\s*:', text.lower()):
        for raw in lines:
            q = _extract_ft_line_quota(raw.strip())
            if q:
                result['quota'] = q
                break

    # Squadre da testo semplice (solo se non già trovate via 🆚): v/vs preferito su -.
    if not result['teams']:
        result['teams'] = _find_teams(lines)

    return result
