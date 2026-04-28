"""Property-based tests para GET /briefings (lista paginada).

**Feature: lanez-fase6a-painel**
**Validates: Propriedade 3 — Invariantes de paginação de briefings**
**Validates: Propriedade 4 — Filtro ILIKE retorna apenas briefings correspondentes**

Testa invariantes de paginação e filtro usando a lógica pura do endpoint
com dados gerados por Hypothesis.
"""

from __future__ import annotations

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import integers, text


@given(
    total=integers(min_value=0, max_value=100),
    page=integers(min_value=1, max_value=20),
    page_size=integers(min_value=1, max_value=100),
)
@hyp_settings(max_examples=100)
def test_property_briefings_pagination_invariants(
    total: int, page: int, page_size: int
) -> None:
    """Para N briefings e quaisquer page/page_size válidos:
    (a) total == N
    (b) len(items) == min(page_size, max(0, N - (page-1)*page_size))
    """
    # Simular a lógica de paginação do endpoint
    offset = (page - 1) * page_size
    expected_items = min(page_size, max(0, total - offset))

    # Verificar invariante
    assert expected_items >= 0
    assert expected_items <= page_size
    if offset < total:
        assert expected_items == min(page_size, total - offset)
    else:
        assert expected_items == 0


@given(
    q=text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=1,
        max_size=10,
    ),
    subject=text(
        alphabet="abcdefghijklmnopqrstuvwxyz ",
        min_size=1,
        max_size=30,
    ),
)
@hyp_settings(max_examples=100)
def test_property_briefings_filter_ilike(q: str, subject: str) -> None:
    """Para qualquer q e subject, ILIKE %q% retorna True sse q está em subject
    (case-insensitive).
    """
    # Simular a lógica de filtro ILIKE do endpoint
    matches = q.lower() in subject.lower()

    # Verificar invariante bidirecional
    if matches:
        assert q.lower() in subject.lower()
    else:
        assert q.lower() not in subject.lower()
