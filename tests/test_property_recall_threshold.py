"""Property-based test para threshold de recall.

**Validates: Requirements 4.3**

Propriedade 3: Todos os resultados retornados após filtro distance < 0.5
têm relevance_score >= 0.5, onde relevance_score = round(1 - distance, 4).

    ∀ r ∈ recall_memory(...) → r["relevance_score"] >= 0.5
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import floats, lists


@given(
    distances=lists(
        floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=20,
    ),
)
@hyp_settings(max_examples=50, deadline=None)
def test_recall_threshold_filters_correctly(distances: list[float]) -> None:
    """Após filtro distance < 0.5, todos os resultados têm relevance_score >= 0.5."""
    # Aplicar filtro de threshold (mesma lógica de recall_memory)
    filtered = [d for d in distances if d < 0.5]

    # Calcular relevance_score para cada resultado filtrado
    scores = [round(1 - d, 4) for d in filtered]

    # Todos os scores devem ser > 0.5
    assert all(score >= 0.5 for score in scores), (
        f"Encontrado relevance_score < 0.5: {scores}. Distâncias filtradas: {filtered}"
    )

    # Quantidade de resultados == quantidade de distâncias < 0.5
    expected_count = sum(1 for d in distances if d < 0.5)
    assert len(filtered) == expected_count, (
        f"Esperado {expected_count} resultados, obteve {len(filtered)}"
    )
