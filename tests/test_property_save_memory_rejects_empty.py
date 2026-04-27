"""Property-based test para rejeição de content vazio em save_memory.

**Validates: Requirements 3.5**

Propriedade 5: save_memory com content vazio ou só whitespace sempre
levanta ValueError, sem executar operação no banco.

    ∀ c ∈ String, c.strip() == "" → save_memory(..., content=c) raises ValueError
"""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import from_regex


@given(content=from_regex(r"^[\s\t\n\r]*$", fullmatch=True))
@hyp_settings(max_examples=50, deadline=None)
def test_save_memory_rejects_empty_content(content: str) -> None:
    """save_memory com content whitespace levanta ValueError sem tocar o banco."""
    user_id = uuid.uuid4()

    db = AsyncMock()

    from app.services.memory import save_memory

    with pytest.raises(ValueError):
        asyncio.run(save_memory(db, user_id, content))

    # db.add nunca deve ser chamado
    db.add.assert_not_called()
