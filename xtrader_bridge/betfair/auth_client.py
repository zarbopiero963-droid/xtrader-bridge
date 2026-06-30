"""Client di autenticazione Betfair.it (issue #86 PR-P4) — read-only, token in RAM.

Login non-interattivo Betfair.it con **certificato** (cert + private key) e
**Delayed App Key**, su `identitysso-cert.betfair.it/api/certlogin`. Vincoli:

- il `sessionToken` ottenuto vive **solo in RAM** (`BetfairSession`): mai su disco,
  mai nei log (è registrato nel redattore globale);
- **nessuna operazione di scommessa**: l'unica operazione è il login/logout; passa
  comunque dal guard `safety.assert_read_only` per contratto;
- **errori safe**: in caso di fallimento si solleva `LoginError`/`CertificateError`
  senza mai incorporare la response grezza, gli header o i segreti nel messaggio.

La chiamata HTTP reale usa solo la **stdlib** (`urllib` + `ssl.load_cert_chain`):
nessuna nuova dipendenza. È isolata in `_default_transport` e **iniettabile** via
`transport=`, così i test girano offline con un trasporto finto e il percorso di
rete reale resta una verifica manuale (Windows, certificato vero).
"""

import json
import os

from . import credential_store, safety
from .credential_store import BetfairCredentials
from .session import BetfairSession

# Endpoint di login con certificato del dominio italiano.
CERTLOGIN_URL = "https://identitysso-cert.betfair.it/api/certlogin"

# Endpoint di logout Betfair: invalida la sessione lato SERVER (issue #168). Il logout NON usa
# il certificato (basta il sessionToken in `X-Authentication` + l'App Key in `X-Application`).
LOGOUT_URL = "https://identitysso.betfair.it/api/logout"

# Nome "operazione" per il guard read-only (NON è un'operazione di scommessa).
LOGIN_OPERATION = "certlogin"

# Timeout della richiesta di login (secondi): un login non deve bloccare all'infinito.
LOGIN_TIMEOUT = 20

# Timeout del logout (secondi): più corto del login — è best-effort e non deve far attendere
# l'utente/teardown auto-sync a lungo se il server non risponde.
LOGOUT_TIMEOUT = 10


class LoginError(RuntimeError):
    """Login Betfair non riuscito (credenziali errate, rete, stato != SUCCESS).

    Il messaggio è sempre **safe**: non contiene response grezza, header o segreti."""


class CertificateError(LoginError):
    """Certificato / private key mancanti o non trovati su disco."""


def _default_transport(creds: BetfairCredentials) -> dict:
    """Esegue il certlogin reale via stdlib e ritorna il JSON di risposta come dict.

    Usa un `ssl.SSLContext` con `load_cert_chain` (autenticazione TLS client) e POST
    urlencoded. Non logga nulla. Importata lazy così l'assenza di rete/SSL non pesa
    sull'import del modulo."""
    import ssl
    import urllib.parse
    import urllib.request

    ctx = ssl.create_default_context()
    ctx.load_cert_chain(certfile=creds.cert_path, keyfile=creds.key_path)
    body = urllib.parse.urlencode(
        {"username": creds.username, "password": creds.password}).encode("utf-8")
    req = urllib.request.Request(
        CERTLOGIN_URL, data=body, method="POST",
        headers={
            "X-Application": creds.app_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=LOGIN_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw)


def _default_logout_transport(token: str, app_key: str) -> None:
    """POST al logout endpoint Betfair per invalidare il `sessionToken` lato SERVER (#168).

    Usa solo la stdlib. Non logga nulla e scarta il corpo della risposta (può contenere lo
    stato della sessione). Importata lazy come `_default_transport`."""
    import urllib.request

    req = urllib.request.Request(
        LOGOUT_URL, data=b"", method="POST",
        headers={
            "X-Authentication": token,
            "X-Application": app_key or "",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=LOGOUT_TIMEOUT) as resp:
        resp.read()   # consuma e scarta: nessun contenuto loggato


class BetfairAuthClient:
    """Login/logout Betfair.it con certificato. Custodisce il token in RAM.

    `session`: la `BetfairSession` condivisa col bridge. `transport`: callable
    `(BetfairCredentials) -> dict` per iniettare un trasporto finto nei test; se
    ``None`` usa `_default_transport` (rete reale)."""

    def __init__(self, session: BetfairSession = None, transport=None, logout_transport=None):
        self.session = session if session is not None else BetfairSession()
        self._transport = transport
        # Trasporto del logout server-side, iniettabile nei test (callable `(token, app_key)`);
        # se ``None`` usa `_default_logout_transport` (rete reale).
        self._logout_transport = logout_transport

    @property
    def is_logged_in(self) -> bool:
        return self.session.is_logged_in

    def login(self, creds: BetfairCredentials = None) -> str:
        """Esegue il login e mette il `sessionToken` in RAM; lo ritorna.

        Se `creds` è ``None`` carica le credenziali locali cifrate dal keyring.
        Solleva `CertificateError` se cert/key mancano o non esistono,
        `LoginError` se le credenziali sono incomplete, la rete fallisce o lo stato
        di login non è ``SUCCESS``. Nessun dato sensibile finisce nel messaggio."""
        # Contratto read-only: il login NON è una operazione di scommessa.
        safety.assert_read_only(LOGIN_OPERATION)

        if creds is None:
            creds = credential_store.load_credentials()

        if not (creds.app_key.strip() and creds.username.strip()
                and creds.password.strip()):
            raise LoginError("Credenziali Betfair incomplete (App Key/username/password).")
        if not (creds.cert_path.strip() and creds.key_path.strip()):
            raise CertificateError("Certificato o private key non configurati.")
        if not (os.path.isfile(creds.cert_path) and os.path.isfile(creds.key_path)):
            raise CertificateError("File certificato/private key non trovati su disco.")

        transport = self._transport or _default_transport
        try:
            data = transport(creds)
        except CertificateError:
            raise
        except Exception as ex:   # noqa: BLE001 — errore safe: niente response/segreti nel messaggio
            # Solo il TIPO dell'errore, mai il contenuto (può includere body/header). `from None`
            # SOPPRIME la causa (#168, Codex): con `from ex` l'eccezione originale del trasporto
            # resterebbe in `__cause__` e un traceback / `logger.exception(exc_info=True)`
            # stamperebbe il suo messaggio grezzo (potenzialmente body/segreti del login).
            raise LoginError(
                f"Login Betfair fallito ({type(ex).__name__}).") from None

        status = (data or {}).get("loginStatus")
        token = (data or {}).get("sessionToken")
        if status != "SUCCESS" or not token:
            # `status` è un codice safe (es. INVALID_USERNAME_OR_PASSWORD), non un segreto.
            raise LoginError(f"Login Betfair non riuscito: {status or 'risposta non valida'}.")

        self.session.set_token(token)   # solo in RAM + registrato per la redazione log
        return token

    def logout(self, creds: BetfairCredentials = None) -> None:
        """Logout: invalida la sessione **lato server** (best-effort) e poi cancella il
        `sessionToken` dalla RAM (idempotente). Le credenziali salvate non vengono toccate.

        Senza la chiamata server-side il token resterebbe valido fino alla scadenza naturale
        anche dopo il logout locale (#168): un token "loggato fuori" ma ancora vivo è un rischio.
        La chiamata di rete è **best-effort** — un suo fallimento (rete, server) NON deve
        impedire la pulizia della RAM, altrimenti l'utente resterebbe "connesso" localmente.

        `creds` serve solo per l'`X-Application` (App Key); se ``None`` viene caricato dal keyring
        (`load_credentials` è già fail-safe e non solleva)."""
        token = self.session.token
        if token:
            if creds is None:
                creds = credential_store.load_credentials()
            app_key = creds.app_key.strip() if creds else ""
            transport = self._logout_transport or _default_logout_transport
            try:
                transport(token, app_key)
            except Exception:   # noqa: BLE001 — logout server best-effort: niente crash/segreti, la RAM si pulisce comunque
                pass
        self.session.clear()
