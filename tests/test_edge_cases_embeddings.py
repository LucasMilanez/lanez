"""Testes de casos de borda para o serviço de embeddings.

Caso de Borda 1: Texto vazio em ingest_item (R6.2)
Caso de Borda 2: Texto longo com múltiplos chunks (R5)
Caso de Borda 3: Texto sem parágrafos (R5.4)
Caso de Borda 4: Busca semântica sem embeddings (R7)
Caso de Borda 5: Busca semântica com serviço inexistente (R7.4)
Caso de Borda 8: content_hash igual (skip) — ingest_item retorna False na segunda chamada (R6.4)
Caso de Borda A2: Limpeza de órfãos em ingest_graph_data (R3)
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import hashlib

from sqlalchemy.dialects import postgresql

from app.services.embeddings import chunk_text, ingest_graph_data, ingest_item, semantic_search


# ---------------------------------------------------------------------------
# Caso de Borda 1: Texto vazio em ingest_item (R6.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_item_empty_string_returns_false():
    """ingest_item com texto vazio deve retornar False sem operação no banco."""
    db = AsyncMock()

    result = await ingest_item(
        db=db,
        user_id=uuid.uuid4(),
        service="mail",
        resource_id="res-1",
        text="",
    )

    assert result is False
    db.execute.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_item_whitespace_only_returns_false():
    """ingest_item com texto só de espaços deve retornar False sem operação no banco."""
    db = AsyncMock()

    result = await ingest_item(
        db=db,
        user_id=uuid.uuid4(),
        service="calendar",
        resource_id="res-2",
        text="   \t\n  ",
    )

    assert result is False
    db.execute.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Caso de Borda 2: Texto longo com múltiplos chunks (R5)
# ---------------------------------------------------------------------------


def test_chunk_text_long_text_returns_multiple_chunks():
    """Texto de ~5000 chars com parágrafos deve gerar múltiplos chunks."""
    # Criar texto com parágrafos distintos totalizando ~5000 chars
    paragraphs = [f"Parágrafo {i}: " + "Lorem ipsum dolor sit amet. " * 20 for i in range(10)]
    long_text = "\n\n".join(paragraphs)

    # Garantir que o texto tem pelo menos 5000 chars
    assert len(long_text) >= 5000, f"Texto gerado tem apenas {len(long_text)} chars"

    chunks = chunk_text(long_text, max_chars=1200)

    assert len(chunks) > 1, "Texto de 5000+ chars deve gerar múltiplos chunks"
    for chunk in chunks:
        assert len(chunk) > 0, "Nenhum chunk deve ser vazio"


# ---------------------------------------------------------------------------
# Caso de Borda 3: Texto sem parágrafos (R5.4)
# ---------------------------------------------------------------------------


def test_chunk_text_no_paragraphs_returns_single_chunk():
    """Texto contínuo sem '\\n\\n' deve retornar exatamente 1 chunk com o texto inteiro.

    Quando não há separador de parágrafo, chunk_text não pode dividir o texto,
    então retorna o bloco inteiro como um único chunk — preservando parágrafos inteiros.
    """
    continuous_text = "A" * 2000
    max_chars = 1200

    chunks = chunk_text(continuous_text, max_chars=max_chars)

    # Sem \n\n, o texto é tratado como um único parágrafo indivisível
    assert len(chunks) == 1
    assert chunks[0] == continuous_text


def test_chunk_text_no_paragraphs_short_text():
    """Texto contínuo curto sem '\\n\\n' deve retornar o texto inteiro em 1 chunk."""
    short_text = "Este é um texto curto sem parágrafos duplos."
    max_chars = 1200

    chunks = chunk_text(short_text, max_chars=max_chars)

    assert chunks == [short_text]
    assert len(chunks) == 1


def test_chunk_text_no_paragraphs_whitespace_only_returns_truncated():
    """Texto só de espaços (sem parágrafos após strip) usa fallback [text[:max_chars]]."""
    whitespace_text = "   \n\n   \n\n   "
    max_chars = 5

    chunks = chunk_text(whitespace_text, max_chars=max_chars)

    # Todos os parágrafos são vazios após strip → fallback [text[:max_chars]]
    assert chunks == [whitespace_text[:max_chars]]
    assert len(chunks) == 1


def test_chunk_text_no_paragraphs_with_single_newlines():
    """Texto com \\n simples (sem \\n\\n) deve ser tratado como bloco único."""
    text_with_newlines = "Linha 1\nLinha 2\nLinha 3\n" * 100
    max_chars = 200

    chunks = chunk_text(text_with_newlines, max_chars=max_chars)

    # Sem \n\n, o split gera um único parágrafo (após strip) — retorna bloco inteiro
    assert len(chunks) == 1
    # O texto é retornado como parágrafo único (stripped)
    assert chunks[0] == text_with_newlines.strip()


# ---------------------------------------------------------------------------
# Caso de Borda 4: Busca semântica sem embeddings no banco (R7)
# ---------------------------------------------------------------------------


def test_semantic_search_no_embeddings_returns_empty_list():
    """semantic_search com user_id sem embeddings no banco deve retornar lista vazia."""
    fake_vector = [0.0] * 384
    user_id = uuid.uuid4()

    # Mock do db.execute → result.all() retorna lista vazia (sem embeddings)
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = []
    db.execute.return_value = result_mock

    with patch("app.services.embeddings.generate_embedding", return_value=fake_vector):
        results = asyncio.run(semantic_search(db, user_id, "qualquer busca"))

    assert results == []
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Caso de Borda 5: Busca semântica com serviço inexistente (R7.4)
# ---------------------------------------------------------------------------


def test_semantic_search_nonexistent_service_returns_empty_list():
    """semantic_search com services=["inexistente"] deve retornar lista vazia.

    Quando o filtro de serviços contém um valor que não corresponde a nenhum
    embedding armazenado, a query SQL simplesmente não encontra resultados.
    """
    fake_vector = [0.0] * 384
    user_id = uuid.uuid4()

    # Mock do db.execute → result.all() retorna lista vazia (nenhum serviço "inexistente")
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = []
    db.execute.return_value = result_mock

    with patch("app.services.embeddings.generate_embedding", return_value=fake_vector):
        results = asyncio.run(
            semantic_search(db, user_id, "qualquer busca", services=["inexistente"])
        )

    assert results == []
    assert isinstance(results, list)

# ---------------------------------------------------------------------------
# Caso de Borda 6: Erro no re-embedding background (R10.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reingest_background_logs_error_on_fetch_failure():
    """_reingest_background deve logar erro e encerrar sem propagar exceção quando fetch_data falha."""
    from fastapi import HTTPException

    from app.routers.webhooks import _reingest_background
    from app.schemas.graph import ServiceType

    user_id = uuid.uuid4()
    service_type = ServiceType.MAIL

    # Mock AsyncSessionLocal como async context manager
    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_redis = MagicMock()

    with (
        patch("app.routers.webhooks.AsyncSessionLocal", return_value=mock_session_ctx),
        patch("app.routers.webhooks.get_redis", return_value=mock_redis),
        patch("app.routers.webhooks.GraphService") as mock_graph_cls,
        patch("app.routers.webhooks.logger") as mock_logger,
    ):
        mock_graph_instance = AsyncMock()
        mock_graph_instance.fetch_data = AsyncMock(
            side_effect=HTTPException(status_code=401)
        )
        mock_graph_instance.close = AsyncMock()
        mock_graph_cls.return_value = mock_graph_instance

        # Chamar _reingest_background — NÃO deve propagar exceção
        await _reingest_background(user_id, service_type)

        # Verificar que o erro foi logado
        mock_logger.exception.assert_called_once()
        log_msg = mock_logger.exception.call_args[0][0]
        assert "Erro no re-embedding" in log_msg

        # Verificar que graph_svc.close() foi chamado no finally
        mock_graph_instance.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Caso de Borda 8: content_hash igual (skip) — segunda ingestão retorna False (R6.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_item_same_text_returns_false_on_second_call():
    """ingest_item com mesmo texto deve retornar False na segunda chamada (deduplicação por content_hash)."""
    user_id = uuid.uuid4()
    service = "mail"
    resource_id = "res-dup-1"
    text = "Conteúdo que não muda entre chamadas"
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    fake_vector = [0.1] * 384

    # --- Primeira chamada: embedding não existe → INSERT ---
    db_first = AsyncMock()
    # db.execute → result.scalar_one_or_none() retorna None (não existe)
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = None
    db_first.execute.return_value = first_result

    with patch("app.services.embeddings.generate_embedding", return_value=fake_vector):
        result_first = await ingest_item(db_first, user_id, service, resource_id, text)

    assert result_first is True
    db_first.add.assert_called_once()
    # After M1, ingest_item no longer commits — commit is handled by get_db
    db_first.commit.assert_not_awaited()

    # --- Segunda chamada: embedding existe com mesmo content_hash → SKIP ---
    db_second = AsyncMock()
    existing_embedding = MagicMock()
    existing_embedding.content_hash = content_hash
    second_result = MagicMock()
    second_result.scalar_one_or_none.return_value = existing_embedding
    db_second.execute.return_value = second_result

    with patch("app.services.embeddings.generate_embedding", return_value=fake_vector):
        result_second = await ingest_item(db_second, user_id, service, resource_id, text)

    assert result_second is False
    db_second.add.assert_not_called()
    db_second.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Caso de Borda A2: Limpeza de órfãos em ingest_graph_data (R3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_graph_data_cleans_orphan_chunks_on_resize():
    """ingest_graph_data deve emitir DELETE de órfãos antes de re-ingerir.

    Validates: Requirements R3 (Issue A2)

    Quando um recurso é re-ingerido, o primeiro db.execute deve ser um DELETE
    que cobre tanto resource_id exato quanto variantes __chunk_N.
    """
    user_id = uuid.uuid4()
    service = "mail"
    resource_id = "abc"
    fake_vector = [0.1] * 384

    db = AsyncMock()
    # ingest_item faz db.execute (SELECT) → precisa retornar mock com scalar_one_or_none
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    db.execute.return_value = select_result

    with (
        patch("app.services.embeddings.extract_text", return_value="Texto curto para um chunk"),
        patch("app.services.embeddings.generate_embedding", return_value=fake_vector),
    ):
        await ingest_graph_data(db, user_id, service, resource_id, {"subject": "test"})

    # O primeiro db.execute deve ser o DELETE de órfãos
    assert db.execute.call_count >= 1, "db.execute deve ter sido chamado ao menos uma vez"

    first_call_args = db.execute.call_args_list[0]
    delete_stmt = first_call_args[0][0]  # primeiro argumento posicional

    # Compilar o statement para SQL com literal_binds para inspecionar valores
    compiled = delete_stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql_literal = str(compiled)

    assert "resource_id = 'abc'" in sql_literal, (
        f"DELETE deve conter resource_id = 'abc'. SQL: {sql_literal}"
    )
    # psycopg2 dialect escapa % como %% em literal_binds
    assert (
        "resource_id LIKE 'abc__chunk_%'" in sql_literal
        or "resource_id LIKE 'abc__chunk_%%'" in sql_literal
    ), (
        f"DELETE deve conter resource_id LIKE 'abc__chunk_%'. SQL: {sql_literal}"
    )
