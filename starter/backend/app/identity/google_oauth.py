from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import InvalidTokenError

from app.core.config import Settings

GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"


class GoogleOIDCError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str


class GoogleOIDCClient:
    def __init__(self, config: Settings) -> None:
        self._config = config

    def authorization_url(self, *, state: str, code_challenge: str, nonce: str) -> str:
        query = urlencode(
            {
                "client_id": self._config.google_client_id,
                "redirect_uri": self._config.google_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self._config.google_client_id,
                        "client_secret": self._config.google_client_secret,
                        "redirect_uri": self._config.google_redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": code_verifier,
                    },
                )
        except httpx.HTTPError as exc:
            raise GoogleOIDCError("GOOGLE_OAUTH_UNAVAILABLE") from exc
        if response.status_code >= 400:
            print(f"[GOOGLE_OAUTH] exchange_code error {response.status_code}: {response.text}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_CODE_INVALID")
        try:
            payload = response.json()
        except ValueError as exc:
            print(f"[GOOGLE_OAUTH] exchange_code invalid json: {exc}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_INVALID_RESPONSE") from exc
        id_token = payload.get("id_token") if isinstance(payload, dict) else None
        if not isinstance(id_token, str) or not id_token:
            print(f"[GOOGLE_OAUTH] exchange_code missing id_token in payload: {payload}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_INVALID_RESPONSE")
        return id_token

    async def fetch_jwks(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(GOOGLE_JWKS_URL)
        except httpx.HTTPError as exc:
            raise GoogleOIDCError("GOOGLE_OAUTH_UNAVAILABLE") from exc
        if response.status_code >= 400:
            raise GoogleOIDCError("GOOGLE_OAUTH_UNAVAILABLE")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleOIDCError("GOOGLE_OAUTH_INVALID_RESPONSE") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise GoogleOIDCError("GOOGLE_OAUTH_INVALID_RESPONSE")
        return payload

    async def validate_id_token(self, *, id_token: str, nonce: str) -> GoogleIdentity:
        try:
            header = jwt.get_unverified_header(id_token)
        except InvalidTokenError as exc:
            print(f"[GOOGLE_OAUTH] validate_id_token header error: {exc}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_TOKEN_INVALID") from exc
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str):
            print(f"[GOOGLE_OAUTH] validate_id_token invalid alg/kid: alg={header.get('alg')} kid={kid}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_TOKEN_INVALID")
        jwks = await self.fetch_jwks()
        jwk = next((key for key in jwks["keys"] if key.get("kid") == kid), None)
        if not isinstance(jwk, dict):
            print(f"[GOOGLE_OAUTH] validate_id_token jwk not found for kid: {kid}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_TOKEN_INVALID")
        try:
            signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            claims = jwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=self._config.google_client_id,
                issuer=list(GOOGLE_ISSUERS),
                options={"require": ["exp", "iat", "iss", "aud", "sub", "email", "nonce"]},
                leeway=30,
            )
        except InvalidTokenError as exc:
            print(f"[GOOGLE_OAUTH] validate_id_token InvalidTokenError: {exc}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_TOKEN_INVALID") from exc
        if claims.get("nonce") != nonce:
            print(f"[GOOGLE_OAUTH] validate_id_token nonce mismatch: claims={claims.get('nonce')} expected={nonce}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_TOKEN_INVALID")
        subject = claims.get("sub")
        email = claims.get("email")
        email_verified = claims.get("email_verified")
        if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
            print(f"[GOOGLE_OAUTH] validate_id_token missing subject or email", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_TOKEN_INVALID")
        if email_verified is not True and email_verified != "true":
            print(f"[GOOGLE_OAUTH] validate_id_token email_verified is not True: {email_verified}", flush=True)
            raise GoogleOIDCError("GOOGLE_OAUTH_EMAIL_UNVERIFIED")
        name = claims.get("name")
        return GoogleIdentity(
            subject=subject,
            email=email.casefold().strip(),
            name=name.strip() if isinstance(name, str) and name.strip() else email.split("@", 1)[0],
        )


def create_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
