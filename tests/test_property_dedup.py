"""Property-based test para deduplicação por content_hash.

**Validates: Requirements 6.4**

Propriedade 4: Chamar ingest_item duas vezes com o mesmo texto para o mesmo
(user_id, service, resource_id) deve retornar True na primeira chamada e
False na segunda chamada (deduplicação por content_hash idêntico).

    ingest_item(db, uid, svc, rid, text) == True   (primeira vez — insert)
    ingest_item(db, uid, svc, rid, text) == False   (segunda vez — skip)
"""

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import text

from app.services.embeddings import ingest_item


def _make_mock_db_for_insert():
    """Cria mock de AsyncSession que simula banco vazio (nenhum embedding existente)."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    return db


def _make_mock_db_for_dedup(content_hash: str):
    """Cria mock de AsyncSession que simula embedding existente com mesmo content_hash."""
    db = AsyncMock()
    existing = MagicMock()
    existing.content_hash = content_hash
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute.return_value = result
    return db


@given(input_text=text(min_size=1))
@hyp_settings(max_examples=50, deadline=None)
def test_dedup_second_call_returns_false(input_text: str) -> None:
    """Ingerir o mesmo texto duas vezes deve retornar True e depois False.

    Simula o fluxo completo de deduplicação:
    1ª chamada — banco vazio → insert → retorna True
    2ª chamada — embedding existe com mesmo hash → skip → retorna False
    """
    # Pular strings que ficam vazias após strip (ingest_item retorna False para texto vazio)
    if not input_text.strip():
        return

    user_id = uuid.uuid4()
    service = "mail"
    resource_id = "test-resource-id"
    content_hash = hashlib.sha256(input_text.encode()).hexdigest()
    fake_vector = [0.0] * 384

    with patch("app.services.embeddings.generate_embedding", return_value=fake_vector):
        # 1ª chamada: banco vazio → insert → True
        db_insert = _make_mock_db_for_insert()
        db_insert.add = MagicMock()  # add é síncrono no SQLAlchemy
        first_result = asyncio.run(
            ingest_item(db_insert, user_id, service, resource_id, input_text)
        )
        assert first_result is True, (
            f"Primeira ingestão deveria retornar True, obteve {first_result}"
        )

        # 2ª chamada: embedding existe com mesmo hash → skip → False
        db_dedup = _make_mock_db_for_dedup(content_hash)
        second_result = asyncio.run(
            ingest_item(db_dedup, user_id, service, resource_id, input_text)
        )
        assert second_result is False, (
            f"Segunda ingestão com mesmo texto deveria retornar False, obteve {second_result}"
        )
