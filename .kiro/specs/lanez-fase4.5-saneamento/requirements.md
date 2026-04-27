# Documento de Requisitos — Lanez Fase 4.5: Saneamento Técnico

## Introdução

A Fase 4.5 é exclusivamente saneamento técnico. Não há feature nova, tabela nova ou tool MCP nova. O escopo são 5 issues de dívida técnica acumuladas nas Fases 1–4 que não trancam funcionalidade hoje mas viram bugs reais em deploy contra Postgres, em CI ao longo do tempo, ou bloqueiam composição transacional em fases futuras.

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Embeddings_Órfãos**: Registros na tabela `embeddings` que referenciam chunks de uma versão anterior de um recurso e não são mais válidos após re-ingestão com número diferente de chunks
- **Server_Default**: Parâmetro `server_default=` do SQLAlchemy que gera cláusula `DEFAULT` no DDL SQL — diferente de `default=` que é Python-side only
- **Composição_Transacional**: Padrão onde múltiplas operações de serviço compõem uma única transação de banco, com commit/rollback gerenciado pelo caller (router/dependency)
- **Flush**: Operação SQLAlchemy que envia SQL ao banco (INSERT/UPDATE) sem commitar a transação — permite `refresh()` para popular campos gerados pelo banco
- **Banker's_Rounding**: Comportamento de `round()` em Python onde `.5` arredonda para o par mais próximo (ex: `round(0.5, 0)` → 0, `round(1.5, 0)` → 2)
- **pgvector**: Extensão PostgreSQL para armazenamento e busca de vetores — requer tipo `vector(N)` para índices HNSW
- **HNSW**: Hierarchical Navigable Small World — algoritmo de índice para busca vetorial aproximada, requer coluna do tipo `vector(N)` (não `text`)

## Requisitos

### Requisito R1 (Issue C1): Coluna vector deve ser Vector(384) nas migrations

**User Story:** Como desenvolvedor fazendo deploy em Postgres real, quero que as migrations usem o tipo `Vector(384)` do pgvector na coluna `vector`, para que `alembic upgrade head` não falhe ao criar índices HNSW.

#### Critérios de Aceitação

1. WHEN a migration `002_add_embeddings.py` é executada, THE Sistema SHALL usar `Vector(384)` (importado de `pgvector.sqlalchemy`) como tipo da coluna `vector` na tabela `embeddings`
2. WHEN a migration `003_add_memories.py` é executada, THE Sistema SHALL usar `Vector(384)` (importado de `pgvector.sqlalchemy`) como tipo da coluna `vector` na tabela `memories`
3. THE migrations 002 e 003 SHALL importar `from pgvector.sqlalchemy import Vector` no topo do arquivo
4. THE Sistema SHALL manter o `CREATE INDEX ... USING hnsw (vector vector_cosine_ops)` inalterado (raw SQL já correto)
5. THE Sistema SHALL NÃO modificar os modelos SQLAlchemy em `app/models/embedding.py` e `app/models/memory.py` (já usam `Vector(384)` corretamente)

### Requisito R2 (Issue A1): Property test recall_threshold não deve ser flaky

**User Story:** Como desenvolvedor rodando CI, quero que o property test `test_recall_threshold_filters_correctly` passe deterministicamente para qualquer seed do Hypothesis, para que não haja falhas aleatórias em CI.

#### Critérios de Aceitação

1. THE teste `test_recall_threshold_filters_correctly` SHALL usar `score >= 0.5` (não `score > 0.5`) no assert principal
2. THE teste SHALL passar para seeds de 0 a 20 (`pytest tests/test_property_recall_threshold.py --hypothesis-seed=N`)
3. THE Sistema SHALL NÃO modificar o serviço `recall_memory` em `app/services/memory.py` — o filtro `distance < 0.5` e `round(1 - distance, 4)` permanecem inalterados

### Requisito R3 (Issue A2): Re-ingestão deve limpar embeddings órfãos

**User Story:** Como usuário cujo conteúdo é re-ingerido após edição, quero que embeddings de chunks antigos sejam removidos antes da nova ingestão, para que a busca semântica não retorne trechos desatualizados.

#### Critérios de Aceitação

1. WHEN `ingest_graph_data` é chamado com texto não vazio, THE Sistema SHALL executar um DELETE que remove todas as entradas com `(user_id, service, resource_id == X OR resource_id LIKE 'X__chunk_%')` ANTES de re-ingerir
2. THE DELETE SHALL cobrir tanto o resource_id exato quanto variantes com sufixo `__chunk_N`, eliminando Embeddings_Órfãos independente da direção da mudança (1→N, N→1, N→M)
3. THE Sistema SHALL ter um teste em `tests/test_edge_cases_embeddings.py` que valida a limpeza de órfãos quando um recurso muda de N chunks para 1 chunk
4. THE Sistema SHALL NÃO executar o DELETE quando `extract_text` retorna string vazia (early return mantido)

### Requisito R4 (Issue M1): Services não devem chamar commit() diretamente

**User Story:** Como desenvolvedor implementando features futuras, quero que os services façam flush (não commit), para que múltiplas operações possam compor uma única transação atômica gerenciada pelo caller.

#### Critérios de Aceitação

1. THE `get_db()` em `app/database.py` SHALL fazer commit automático ao final do request (no exit normal do generator) e rollback automático em caso de exceção — padrão Composição_Transacional
2. THE `ingest_item` em `app/services/embeddings.py` SHALL NÃO chamar `await db.commit()`
3. THE `save_memory` em `app/services/memory.py` SHALL NÃO chamar `await db.commit()` — SHALL chamar `await db.flush()` seguido de `await db.refresh(memory)` para popular campos gerados
4. THE `recall_memory` em `app/services/memory.py` SHALL NÃO chamar `await db.commit()` (o UPDATE de `last_accessed_at` será commitado pelo `get_db`)
5. THE Sistema SHALL ter um teste em `tests/test_edge_cases_memory.py` (`test_save_memory_does_not_commit`) que valida que `save_memory` chama flush mas não commit
6. THE testes existentes em `tests/test_edge_cases_memory.py` que verificam `db.commit.assert_not_awaited()` SHALL continuar passando (comportamento compatível)

### Requisito R5 (Issue M2): Migrations devem usar server_default para UUIDs

**User Story:** Como DBA executando inserts via SQL puro (psql, dumps, scripts de migração), quero que as colunas `id` tenham `DEFAULT gen_random_uuid()` no DDL, para que inserts sem campo `id` explícito não falhem com violação de not-null.

#### Critérios de Aceitação

1. THE migration `001_initial_tables.py` SHALL usar `server_default=sa.text("gen_random_uuid()")` (não `default=`) nas colunas `id` das tabelas `users`, `graph_cache` e `webhook_subscriptions`
2. THE migration `002_add_embeddings.py` SHALL usar `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `embeddings`
3. THE migration `003_add_memories.py` SHALL usar `server_default=sa.text("gen_random_uuid()")` na coluna `id` da tabela `memories`
4. THE Sistema SHALL NÃO modificar os modelos SQLAlchemy (`app/models/*.py`) — o `default=uuid.uuid4` Python-side permanece como dupla camada
5. THE suíte completa de testes SHALL continuar passando após a mudança
