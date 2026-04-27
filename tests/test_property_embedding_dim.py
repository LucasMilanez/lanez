"""Property-based test para dimensão do vetor de embedding.

**Validates: Requisito 3.5 (generate_embedding retorna lista de exatamente 384 floats)**

Propriedade 1: Para qualquer string não vazia, generate_embedding deve retornar
uma lista de exatamente 384 floats.

    len(generate_embedding(text)) == 384
    all(isinstance(v, float) for v in generate_embedding(text))
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import text

from app.services.embeddings import generate_embedding


@given(input_text=text(min_size=1))
@hyp_settings(max_examples=50, deadline=None)
def test_embedding_always_384_floats(input_text: str) -> None:
    """generate_embedding deve retornar exatamente 384 floats para qualquer string não vazia."""
    result = generate_embedding(input_text)

    assert isinstance(result, list), f"Esperado list, obteve {type(result).__name__}"
    assert len(result) == 384, f"Esperado 384 dimensões, obteve {len(result)}"
    assert all(isinstance(v, float) for v in result), (
        "Todos os elementos devem ser float"
    )
