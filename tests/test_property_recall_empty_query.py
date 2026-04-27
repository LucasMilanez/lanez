"""Property-based test para query vazia em recall_memory.

**Validates: Requirements 4.6**

Propriedade 4: recall_memory com query vazia ou só whitespace sempre
retorna lista vazia, sem executar busca no banco.

    ∀ q ∈ String, q.strip() == "" → recall_memory(..., query=q) == []
"""

import asyncio
import uuid
from unittest.mock import AsyncMock

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import from_regex


@given(query=from_regex(r"^[\s\t\n\r]*$", fullmatch=True))
@hyp_settings(max_examples=50, deadline=None)
def test_recall_memory_empty_query_returns_empty(query: str) -> None:
    """recall_memory com query whitespace retorna [] sem tocar o banco."""
    user_id = uuid.uuid4()

    db = AsyncMock()

    from app.services.memory import recall_memory

    result = asyncio.run(recall_memory(db, user_id, query))

    # Deve retornar lista vazia
    assert result == [], f"Esperado [], obteve {result}"

    # db.execute nunca deve ser chamado
    db.execute.assert_not_called()
