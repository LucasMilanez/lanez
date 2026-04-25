"""Property-based test para round-trip de criptografia de tokens.

**Validates: Requirements 4.1, 4.2, 2.2**

Propriedade 1: Para qualquer string de token arbitrária, criptografar e depois
descriptografar com a mesma chave deve retornar o valor original.

    decrypt(encrypt(token, key), key) == token
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import text

from app.models.user import decrypt_token, encrypt_token


@given(plaintext=text(min_size=0))
@hyp_settings(max_examples=200)
def test_encrypt_decrypt_roundtrip(plaintext: str) -> None:
    """Criptografar e descriptografar qualquer string deve preservar o valor original."""
    ciphertext = encrypt_token(plaintext)
    recovered = decrypt_token(ciphertext)
    assert recovered == plaintext, (
        f"Round-trip falhou: original={plaintext!r}, recovered={recovered!r}"
    )
