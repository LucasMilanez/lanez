"""Property-based test para chunk_text.

**Validates: Requisito 5.2 (chunk_text sempre retorna lista com pelo menos 1 chunk)**

Propriedade 3: Para qualquer texto não vazio e max_chars positivo (min 10),
chunk_text deve retornar uma lista com pelo menos 1 elemento.

    len(chunk_text(text, max_chars)) >= 1
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import integers, text

from app.services.embeddings import chunk_text


@given(
    input_text=text(min_size=1),
    max_chars=integers(min_value=10, max_value=5000),
)
@hyp_settings(max_examples=200)
def test_chunk_text_always_returns_at_least_one_chunk(
    input_text: str,
    max_chars: int,
) -> None:
    """chunk_text deve retornar lista com pelo menos 1 elemento para qualquer texto não vazio."""
    result = chunk_text(input_text, max_chars)

    assert isinstance(result, list), f"Esperado list, obteve {type(result).__name__}"
    assert len(result) >= 1, (
        f"Esperado pelo menos 1 chunk, obteve {len(result)} "
        f"para text={input_text!r}, max_chars={max_chars}"
    )
    assert all(isinstance(c, str) for c in result), (
        "Todos os chunks devem ser strings"
    )
