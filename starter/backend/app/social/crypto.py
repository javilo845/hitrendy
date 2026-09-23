"""Authenticated encryption for the provider tokens we are forced to keep.

A social access token is a bearer credential for somebody else's account. The
database is therefore treated as untrusted storage: what lands in a row is an
AES-256-GCM envelope, and the plaintext exists only inside a request that is
about to hand it to the provider it came from.

Three properties matter more than the cipher choice itself:

* **Versioned.** Every envelope starts with ``v1``. Rotating the scheme later
  means adding a reader, not guessing what an opaque blob used to be.
* **Random nonce per write.** Encrypting the same token twice never produces
  the same ciphertext, so nobody can tell from the rows that two workspaces
  connected the same account.
* **Bound to its row.** The workspace, the provider and the field name travel
  as associated data. A ciphertext copied into another workspace's row, or from
  the refresh column into the access column, fails to authenticate instead of
  silently decrypting into a working credential.

The key is an operator-supplied 32 byte value, base64 encoded. It is never
derived from a password, a client secret or an API key: those are chosen for
other purposes, rotate on other schedules, and would give an attacker who
already holds one credential a second one for free.
"""

from __future__ import annotations

import base64
import binascii
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings, validate_encryption_key
from app.core.errors import AppError

#: Envelope format marker. Present in the stored string, authenticated as part
#: of the associated data, and checked before anything is decoded.
ENVELOPE_VERSION = "v1"

#: 96 bits is the nonce size AES-GCM is specified for; anything else forces the
#: implementation into a slower, less analysed derivation path.
NONCE_BYTES = 12

#: The fields that may hold an envelope. Naming them keeps the associated data
#: closed: a caller cannot invent a purpose that would let two columns share an
#: authentication context.
ACCESS_TOKEN_PURPOSE = "access_token"
REFRESH_TOKEN_PURPOSE = "refresh_token"
_PURPOSES = frozenset({ACCESS_TOKEN_PURPOSE, REFRESH_TOKEN_PURPOSE})


class TokenCipherUnavailable(RuntimeError):
    """The server cannot encrypt or decrypt because the key is missing or bad."""


class TokenDecryptionError(RuntimeError):
    """The stored envelope did not authenticate against the row that holds it.

    Raised for tampering, for truncation, for an envelope moved between rows,
    and for a key that no longer matches what wrote it. The caller cannot tell
    these apart, and deliberately so: every one of them means the connection
    must be treated as unusable rather than half-trusted.
    """


def _cipher_key() -> bytes:
    if not settings.social_token_encryption_key:
        raise TokenCipherUnavailable(
            "SOCIAL_TOKEN_ENCRYPTION_KEY no está configurada."
        )
    try:
        return validate_encryption_key(
            settings.social_token_encryption_key, name="SOCIAL_TOKEN_ENCRYPTION_KEY"
        )
    except RuntimeError as exc:
        raise TokenCipherUnavailable(str(exc)) from exc


@lru_cache(maxsize=4)
def _cipher_for(key: bytes) -> AESGCM:
    return AESGCM(key)


def _aead() -> AESGCM:
    return _cipher_for(_cipher_key())


def _associated_data(*, workspace_id: str, provider: str, purpose: str) -> bytes:
    if purpose not in _PURPOSES:
        raise ValueError(f"Propósito de cifrado desconocido: {purpose!r}")
    if not workspace_id or not provider:
        raise ValueError("El cifrado de tokens exige workspace y proveedor.")
    return f"{ENVELOPE_VERSION}|{workspace_id}|{provider}|{purpose}".encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def encryption_available() -> bool:
    """True when a token could be encrypted right now. Never raises."""

    try:
        _cipher_key()
    except TokenCipherUnavailable:
        return False
    return True


def encrypt_token(
    token: str, *, workspace_id: str, provider: str, purpose: str
) -> str:
    """Return the envelope to store for ``token``.

    The nonce is fresh on every call, so re-encrypting an unchanged token still
    rewrites the row with different bytes.
    """

    if not token:
        raise ValueError("No se cifra un token vacío.")
    aad = _associated_data(workspace_id=workspace_id, provider=provider, purpose=purpose)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _aead().encrypt(nonce, token.encode("utf-8"), aad)
    return f"{ENVELOPE_VERSION}.{_b64(nonce)}.{_b64(ciphertext)}"


def decrypt_token(
    envelope: str, *, workspace_id: str, provider: str, purpose: str
) -> str:
    """Return the token inside ``envelope``, or refuse.

    Every failure -- unknown version, malformed encoding, wrong row, altered
    bytes -- becomes the same :class:`TokenDecryptionError`, because the caller
    must react identically to all of them.
    """

    aad = _associated_data(workspace_id=workspace_id, provider=provider, purpose=purpose)
    parts = envelope.split(".") if envelope else []
    if len(parts) != 3 or parts[0] != ENVELOPE_VERSION:
        raise TokenDecryptionError("Formato de sobre no reconocido.")
    try:
        nonce = _unb64(parts[1])
        ciphertext = _unb64(parts[2])
    except (binascii.Error, ValueError) as exc:
        raise TokenDecryptionError("El sobre almacenado no es decodificable.") from exc
    if len(nonce) != NONCE_BYTES:
        raise TokenDecryptionError("El nonce almacenado no tiene el tamaño esperado.")
    try:
        plaintext = _aead().decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise TokenDecryptionError("El token almacenado no supera la autenticación.") from exc
    return plaintext.decode("utf-8")


def cipher_unavailable_error() -> AppError:
    """The HTTP shape of a server that cannot handle tokens safely.

    503 rather than 500: the deployment is misconfigured, not the request, and
    the message never names the variable an attacker would like to learn about.
    """

    return AppError(
        "SOCIAL_CONNECTIONS_UNAVAILABLE",
        "Las conexiones sociales no están disponibles en este momento.",
        status_code=503,
        retryable=True,
    )
