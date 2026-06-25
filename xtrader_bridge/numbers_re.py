"""Frammenti regex condivisi per i numeri decimali (fonte unica — anti-drift, audit L4).

Quattro moduli (`parser`, `validator`, `custom_pipeline`, `csv_writer`) ripetevano lo
stesso frammento ``\\d+(?:[.,]\\d+)?``: una modifica in uno e non negli altri avrebbe fatto
divergere il riconoscimento dei numeri (quota/Handicap/Price). Qui sta una sola volta; ogni
modulo compone àncore (``^…$``) e segno come gli serve. Modulo foglia: non importa nulla,
nessun rischio di ciclo.
"""

# Numero decimale "puro": cifre con AL PIÙ una parte decimale separata da `.` o `,`
# (niente "1.2.3"/esponenti). Senza segno.
DECIMAL = r"\d+(?:[.,]\d+)?"

# Come `DECIMAL` ma con segno opzionale (es. Handicap "-1"/"+1,5", Price "1.85").
SIGNED_DECIMAL = r"[+-]?\d+(?:[.,]\d+)?"
