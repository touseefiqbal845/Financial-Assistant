import asyncio
import secrets

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

from financial_assistant.config import Settings
from financial_assistant.contracts.models import Scope


class Authenticator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = (
            PyJWKClient(settings.oidc_jwks_url, cache_keys=True, timeout=5)
            if settings.oidc_jwks_url
            else None
        )

    async def authenticate(self, authorization: str | None) -> Scope:
        if (
            not authorization
            or not authorization.startswith("Bearer ")
            or len(authorization) > 8192
        ):
            raise HTTPException(401, "A valid bearer token is required.")
        token = authorization[7:]
        if self.settings.dev_auth_enabled:
            expected = self.settings.dev_token
            if expected and secrets.compare_digest(token, expected.get_secret_value()):
                return Scope(user_id="demo-user", tenant_id="demo", entities=("acme",))
            raise HTTPException(401, "Invalid bearer token.")
        try:
            if self.jwks is None:
                raise ValueError("Identity provider is not configured.")
            key = await asyncio.to_thread(self.jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.settings.oidc_issuer,
                audience=self.settings.oidc_audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud", "tenant_id", "entities"]},
            )
            return Scope(
                user_id=claims["sub"], tenant_id=claims["tenant_id"], entities=claims["entities"]
            )
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(401, "Invalid bearer token.") from exc
