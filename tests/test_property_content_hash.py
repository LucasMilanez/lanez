"""Property-based test para content_hash SHA-256.

**Validates: Requisito 6.3 (content_hash como hashlib.sha256(text.encode()).hexdigest())**

Propriedade 2: Para qualquer string aleatória, o SHA-256 hexdigest deve ter
exatamente 64 caracteres e todos devem ser hexadecimais.

    len(hashlib.sha256(text.encode()).hexdigest()) == 64
    all(c in '0123456789abcdef' for c in hash)
"""

import hashlib

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import text


@given(input_text=text(min_size=0))
@hyp_settings(max_examples=200)
def test_content_hash_sha256_length_and_hex(input_text: str) -> None:
    """content_hash SHA-256 deve ter exatamente 64 caracteres hexadecimais."""
    content_hash = hashlib.sha256(input_text.encode()).hexdigest()

    assert len(content_hash) == 64, (
        f"Esperado 64 caracteres, obteve {len(content_hash)}"
    )
    assert all(c in "0123456789abcdef" for c in content_hash), (
        f"Hash contém caracteres não-hexadecimais: {content_hash}"
    )
