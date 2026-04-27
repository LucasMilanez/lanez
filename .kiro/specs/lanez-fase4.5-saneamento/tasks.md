# Tarefas de Implementação — Lanez Fase 4.5: Saneamento Técnico

## Instrução global de documentação

Após implementar cada tarefa, gere um bloco de explicação com o seguinte formato:

```
### Explicação — Issue X

**Arquivo(s):** `caminho/dos/arquivos.py`

Para cada trecho relevante:
- Cite o trecho (função, linha ou bloco)
- Explique o que mudou e por quê
- Aponte invariante ou restrição que a mudança garante
- Indique o que quebraria se removida
```

---

## Tarefa 1: Issue M2 — server_default em todas as migrations

- [x] 1.1 Em `alembic/versions/001_initial_tables.py`, trocar `default=sa.text("gen_random_uuid()")` por `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `users` (linha 26)
- [x] 1.2 Em `alembic/versions/001_initial_tables.py`, trocar `default=sa.text("gen_random_uuid()")` por `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `graph_cache` (linha 41)
- [x] 1.3 Em `alembic/versions/001_initial_tables.py`, trocar `default=sa.text("gen_random_uuid()")` por `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `webhook_subscriptions` (linha 63)
- [x] 1.4 Em `alembic/versions/002_add_embeddings.py`, trocar `default=sa.text("gen_random_uuid()")` por `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `embeddings` (linha 28)
- [x] 1.5 Em `alembic/versions/003_add_memories.py`, trocar `default=sa.text("gen_random_uuid()")` por `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `memories` (linha 25)

## Tarefa 2: Issue C1 — Vector(384) nas migrations 002 e 003

- [x] 2.1 Em `alembic/versions/002_add_embeddings.py`, adicionar `from pgvector.sqlalchemy import Vector` no topo (após os imports existentes) e trocar `sa.Column("vector", sa.Text(), nullable=False)` por `sa.Column("vector", Vector(384), nullable=False)`
- [x] 2.2 Em `alembic/versions/003_add_memories.py`, adicionar `from pgvector.sqlalchemy import Vector` no topo (após os imports existentes) e trocar `sa.Column("vector", sa.Text(), nullable=False)` por `sa.Column("vector", Vector(384), nullable=False)`

## Tarefa 3: Issue A1 — Assert do property test

- [x] 3.1 Em `tests/test_property_recall_threshold.py`, trocar `assert all(score > 0.5 for score in scores)` por `assert all(score >= 0.5 for score in scores)` e ajustar a mensagem de erro de `"Encontrado relevance_score <= 0.5"` para `"Encontrado relevance_score < 0.5"`

## Tarefa 4: Issue M1 — Refatoração transacional

- [x] 4.1 Em `app/database.py`, ajustar `get_db()` para envolver o `yield session` em try/except: no bloco try, após o yield, chamar `await session.commit()`; no bloco except Exception, chamar `await session.rollback()` e re-raise. Atualizar docstring para documentar o comportamento de commit/rollback automático
- [x] 4.2 Em `app/services/embeddings.py`, função `ingest_item`: remover a linha `await db.commit()` (linha 178). O commit será feito pelo `get_db` no boundary do request
- [x] 4.3 Em `app/services/memory.py`, função `save_memory`: remover `await db.commit()` e substituir por `await db.flush()` (manter `await db.refresh(memory)` logo após o flush)
- [x] 4.4 Em `app/services/memory.py`, função `recall_memory`: remover a linha `await db.commit()` do bloco `if filtered:` (após o UPDATE de last_accessed_at)
- [x] 4.5 Em `tests/test_edge_cases_memory.py`, adicionar teste `test_save_memory_does_not_commit`: mockar db com flush=AsyncMock() e commit=AsyncMock(), chamar save_memory, verificar `db.flush.assert_awaited_once()` e `db.commit.assert_not_awaited()`
- [x] 4.6 Ajustar testes existentes em `tests/test_edge_cases_memory.py` e `tests/test_edge_cases_embeddings.py` que afirmam comportamento de commit: (a) em `test_recall_memory_updates_last_accessed` adicionar `db.commit.assert_not_awaited()`; (b) em `test_ingest_item_same_text_returns_false_on_second_call` trocar `db_first.commit.assert_awaited_once()` por `db_first.commit.assert_not_awaited()` (ingest_item não comita mais); (c) em `test_ingest_item_empty_string_returns_false` e `test_ingest_item_whitespace_only_returns_false` manter `db.commit.assert_not_called()` (continua válido)

## Tarefa 5: Issue A2 — DELETE de órfãos em ingest_graph_data

- [x] 5.1 Em `app/services/embeddings.py`, função `ingest_graph_data`: após o `if not text: return` e antes do `chunks = chunk_text(text)`, adicionar `await db.execute(delete(Embedding).where(Embedding.user_id == user_id, Embedding.service == service, or_(Embedding.resource_id == resource_id, Embedding.resource_id.like(f"{resource_id}__chunk_%"))))`. Adicionar imports necessários: `from sqlalchemy import delete, or_` (se não existirem) e garantir que `Embedding` já está importado
- [x] 5.2 Em `tests/test_edge_cases_embeddings.py`, adicionar teste `test_ingest_graph_data_cleans_orphan_chunks_on_resize`: mockar db.execute (capturando call_args_list), mockar extract_text para retornar texto curto (1 chunk) na chamada, mockar generate_embedding, chamar ingest_graph_data com resource_id="abc", verificar que o primeiro db.execute recebeu um DELETE statement cujo SQL compilado contém `resource_id = 'abc' OR resource_id LIKE 'abc__chunk_%'`
