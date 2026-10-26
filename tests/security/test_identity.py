import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from financial_assistant.security.authentication import Authenticator


async def test_signed_identity_claims_and_audience(settings):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    configured = settings.model_copy(
        update={
            "dev_auth_enabled": False,
            "oidc_jwks_url": "https://identity.example/jwks",
            "oidc_issuer": "https://identity.example",
            "oidc_audience": "finance",
        }
    )
    auth = Authenticator(configured)
    auth.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    claims = {
        "sub": "analyst",
        "tenant_id": "demo",
        "entities": ["acme"],
        "iss": "https://identity.example",
        "aud": "finance",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
    }
    token = jwt.encode(claims, private, algorithm="RS256")
    scope = await auth.authenticate("Bearer " + token)
    assert scope.entities == ("acme",) and scope.user_id == "analyst"
    bad = jwt.encode({**claims, "aud": "other"}, private, algorithm="RS256")
    with pytest.raises(HTTPException) as failure:
        await auth.authenticate("Bearer " + bad)
    assert failure.value.status_code == 401


async def test_expired_and_unsigned_credentials_rejected(settings):
    auth = Authenticator(settings)
    for token in (None, "Bearer invalid", "Bearer " + "a" * 9000):
        with pytest.raises(HTTPException):
            await auth.authenticate(token)
