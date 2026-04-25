"""Property-based test para PKCE Code Challenge.

**Validates: Requirements 1.1**

Propriedade 4: Para todo code_verifier, o code_challenge gerado deve ser
exatamente base64url(SHA256(code_verifier)) sem padding, conforme RFC 7636.

    base64url(sha256(code_verifier)) == code_challenge
"""

import hashlib
import re
from base64 import urlsafe_b64encode

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import binary, integers

from app.routers.auth import _generate_code_challenge, _generate_code_verifier


# Regex para base64url sem padding (RFC 4648 §5)
BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@given(raw_bytes=binary(min_size=16, max_size=64))
@hyp_settings(max_examples=200)
def test_code_challenge_is_sha256_of_verifier(raw_bytes: bytes) -> None:
    """Para qualquer verifier arbitrário, o challenge deve ser base64url(sha256(verifier))."""
    # Construir um verifier válido a partir de bytes aleatórios
    verifier = urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")

    # Calcular challenge usando a função sob teste
    challenge = _generate_code_challenge(verifier)

    # Calcular independentemente: sha256 → base64url sem padding
    expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")

    assert challenge == expected_challenge, (
        f"Challenge mismatch: got {challenge!r}, expected {expected_challenge!r} "
        f"for verifier {verifier!r}"
    )


@given(n=integers(min_value=1, max_value=50))
@hyp_settings(max_examples=200)
def test_generate_code_verifier_produces_valid_base64url(n: int) -> None:
    """code_verifier gerado deve ser uma string base64url válida sem padding."""
    verifier = _generate_code_verifier()

    assert isinstance(verifier, str)
    assert len(verifier) > 0
    assert "=" not in verifier, "code_verifier não deve conter padding '='"
    assert BASE64URL_RE.match(verifier), (
        f"code_verifier contém caracteres inválidos para base64url: {verifier!r}"
    )


@hyp_settings(max_examples=50)
@given(n=integers(min_value=1, max_value=50))
def test_generate_code_verifier_produces_unique_values(n: int) -> None:
    """Múltiplas chamadas a _generate_code_verifier devem produzir valores distintos."""
    verifiers = {_generate_code_verifier() for _ in range(10)}
    assert len(verifiers) == 10, (
        f"Esperados 10 verifiers únicos, obtidos {len(verifiers)}"
    )
