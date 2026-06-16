"""Parsing dei messaggi Telegram P.Bet. (nessuna dipendenza dalla GUI).

PR-09: parser robusto che gestisce messaggi con emoji **e** in testo semplice.
Estrae signal_type, squadre (normalizzate "Home v Away" da v/vs/-), quota
(virgola o punto), score, minuto, probabilità, bet_type (BACK/LAY) e flag live.
NON inventa dati: i campi non presenti restano vuoti (il blocco dei segnali
incompleti — incl. quota mancante — è di recognition/validazione, PR-10).
"""

import re

_HAS_ALPHA = re.compile(r'[A-Za-zÀ-ÿ]')
_EMOJI_MARKERS = ('🏆', '🆚', '⚽', '⌚', '📊', '📈')

# Numero ben formato (no "1.2.3"): intero con al più una parte decimale.
_NUM = r'\d+(?:[.,]\d+)?'

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
_SCORE_TAIL = re.compile(r'\s+\d+\s*[-–:]\s*\d+(?:\s.*)?$')
# Token di stato da togliere dal signal_type (LIVE/PRE) prima del mapping.
_STATUS_TAIL = re.compile(r'\s+\b(?:live|pre|prematch)\b.*$', re.IGNORECASE)


def _extract_quota(line: str):
    """Quota da "Quota X" / "@X" (virgola→punto), numero ben formato."""
    m = re.search(r'(?:quota|@)[:\s]*(' + _NUM + r')', line, re.IGNORECASE)
    return m.group(1).replace(',', '.') if m else None


def _extract_probability(line: str):
    """Probabilità da "...X%" (numero ben formato)."""
    m = re.search(r'(' + _NUM + r')\s*%', line)
    return m.group(1) if m else None


def _bare_number(line: str):
    """Primo numero ben formato della riga (per linee quota con sola emoji)."""
    m = re.search(r'(' + _NUM + r')', line)
    return m.group(1).replace(',', '.') if m else None


def _looks_like_label(line: str) -> bool:
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
    m = sep.match(cleaned)
    if m and _HAS_ALPHA.search(m.group(1)) and _HAS_ALPHA.search(m.group(2)):
        return f"{m.group(1).strip()} v {m.group(2).strip()}"
    return None


def _find_teams(lines) -> str:
    """Cerca la riga squadre: prima con " v "/" vs " (cue forte), poi " - "."""
    for sep in (_SEP_VVS, _SEP_DASH):
        for raw in lines:
            t = _teams_from(raw.strip(), sep)
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

    low = text.lower()
    # bet_type: BANCA/LAY ha priorità su PUNTA/BACK; default BACK.
    if re.search(r'\bbanca\b', low) or re.search(r'\blay\b', low):
        result['bet_type'] = 'LAY'
    elif re.search(r'\bpunta\b', low) or re.search(r'\bback\b', low):
        result['bet_type'] = 'BACK'
    if re.search(r'\blive\b', low):
        result['live'] = True

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
            t = _teams_from(re.sub(r'[🆚]', ' ', line).strip(), _SEP_VVS) \
                or _teams_from(re.sub(r'[🆚]', ' ', line).strip(), _SEP_DASH)
            result['teams'] = t or result['teams']
            continue
        if '⚽' in line:
            result['score'] = re.sub(r'[⚽\s]+', ' ', line).strip()
            continue
        if '⌚' in line:
            result['time_'] = re.sub(r'[⌚\s]+', ' ', line).strip()
            continue
        if '📊' in line or '📈' in line:
            prob = _extract_probability(line)
            if prob:
                if not result['probability']:
                    result['probability'] = prob
            elif '📈' in line and not result['quota']:
                n = _bare_number(line)
                if n:
                    result['quota'] = n
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

    # Squadre da testo semplice (solo se non già trovate via 🆚): v/vs preferito su -.
    if not result['teams']:
        result['teams'] = _find_teams(lines)

    return result
