"""Property-based test para threshold da busca semântica.

**Validates: Requisito 7.5 (descartar resultados com cosine_distance >= 0.5)**

Propriedade 5: Para qualquer conjunto de resultados retornados por semantic_search,
todos devem ter relevance_score > 0.5 (equivalente a cosine_distance < 0.5).

    all(r["relevance_score"] > 0.5 for r in semantic_search(...))
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import floats, lists, text

from app.services.embeddings import semantic_search


def _make_mock_row(distance: float, service: str = "mail", resource_id: str = "res-1") -> MagicMock:
    """Cria mock de uma row retornada pelo db.execute (SELECT Embedding, distance)."""
    row = MagicMock()
    row.Embedding.service = service
    row.Embedding.resource_id = resource_id
    row.distance = distance
    return row


@given(
    distances=lists(
        floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=20,
    ),
    query_text=text(min_size=1, max_size=50),
)
@hyp_settings(max_examples=100, deadline=None)
def test_search_results_always_above_threshold(distances: list[float], query_text: str) -> None:
    """Todos os resultados de semantic_search devem ter relevance_score > 0.5.

    Gera distâncias aleatórias entre 0.0 e 1.0, simula o banco retornando
    essas distâncias, e verifica que a função filtra corretamente os
    resultados com distance >= 0.5.
    """
    fake_vector = [0.0] * 384
    user_id = uuid.uuid4()

    # Criar mock rows com distâncias geradas
    mock_rows = [
        _make_mock_row(d, service="mail", resource_id=f"res-{i}")
        for i, d in enumerate(distances)
    ]

    # Mock do db.execute → result.all() retorna as rows
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = mock_rows
    db.execute.return_value = result_mock

    with patch("app.services.embeddings.generate_embedding", return_value=fake_vector):
        results = asyncio.run(semantic_search(db, user_id, query_text))

    # Propriedade principal: todos os resultados têm relevance_score > 0.5
    assert all(r["relevance_score"] > 0.5 for r in results), (
        f"Encontrado resultado com relevance_score <= 0.5: "
        f"{[r['relevance_score'] for r in results]}"
    )

    # Propriedade complementar: quantidade de resultados == quantidade de distâncias < 0.5
    expected_count = sum(1 for d in distances if d < 0.5)
    assert len(results) == expected_count, (
        f"Esperado {expected_count} resultados (distâncias < 0.5), obteve {len(results)}. "
        f"Distâncias: {distances}"
    )
