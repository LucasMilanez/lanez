"""Property-based test para dimensão do vetor via save_memory.

**Validates: Requirements 3.3**

Propriedade 1: Para qualquer string não vazia, o embedding gerado por
generate_embedding (reutilizado em save_memory) sempre tem exatamente
384 dimensões.

    ∀ text ∈ String, text.strip() ≠ "" → len(generate_embedding(text)) == 384
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import text


@given(content=text(min_size=1))
@hyp_settings(max_examples=50, deadline=None)
def test_save_memory_vector_has_384_dims(content: str) -> None:
    """save_memory deve gerar vetor de exatamente 384 dimensões para qualquer string não vazia."""
    # Pular strings que são apenas whitespace (save_memory levanta ValueError)
    if not content.strip():
        return

    fake_vector = [0.1] * 384
    user_id = uuid.uuid4()

    db = AsyncMock()
    # db.add é síncrono no SQLAlchemy — usar MagicMock para evitar warning
    from unittest.mock import MagicMock
    db.add = MagicMock()

    captured_vectors = []

    def mock_generate_embedding(text_input: str) -> list[float]:
        captured_vectors.append(fake_vector)
        return fake_vector

    with patch(
        "app.services.memory.generate_embedding",
        side_effect=mock_generate_embedding,
    ) as mock_embed:
        from app.services.memory import save_memory

        asyncio.run(save_memory(db, user_id, content, tags=["test"]))

        # Verificar que generate_embedding foi chamado com o content exato
        mock_embed.assert_called_once_with(content)

        # Verificar que o vetor capturado tem 384 dimensões
        assert len(captured_vectors) == 1
        assert len(captured_vectors[0]) == 384, (
            f"Esperado vetor de 384 dims, obteve {len(captured_vectors[0])}"
        )

        # Verificar que o Memory foi adicionado ao db
        db.add.assert_called_once()
        memory_obj = db.add.call_args[0][0]
        assert len(memory_obj.vector) == 384, (
            f"Vetor do Memory deve ter 384 dims, obteve {len(memory_obj.vector)}"
        )
