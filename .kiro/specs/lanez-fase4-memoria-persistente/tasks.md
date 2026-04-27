# Tarefas de Implementação — Lanez Fase 4: Memória Persistente

## Instrução global de documentação

Após implementar cada tarefa, gere um bloco de explicação com o seguinte formato:

```
### Explicação — Tarefa X.Y

**Arquivo:** `caminho/do/arquivo.py`

Para cada trecho relevante do código implementado:
- Cite o trecho (função, classe, linha ou bloco)
- Explique o que faz
- Explique por que foi escolhida essa abordagem (decisão técnica, alternativa descartada, trade-off)

Inclua especificamente:
- Por que essa biblioteca/função foi usada em vez de alternativas
- Qualquer invariante ou restrição de segurança que o código está garantindo
- O que quebraria se esse trecho fosse removido ou alterado
```

Esta instrução não é um item de tarefa — não crie checkboxes para ela. Aplica-se a todas as tarefas abaixo.

---

## Tarefa 1: Modelo Memory e Models Init

- [x] 1.1 Criar `app/models/memory.py` com classe Memory(Base): __tablename__ = "memories", colunas id (Mapped[uuid.UUID] PK default uuid4), user_id (Mapped[uuid.UUID] FK "users.id" ondelete="CASCADE" nullable=False), content (Mapped[str] Text nullable=False), tags (Mapped[list[str]] ARRAY(String) nullable=False default=list), vector (mapped_column Vector(384) nullable=False), created_at (Mapped[datetime] DateTime(timezone=True) nullable=False), last_accessed_at (Mapped[datetime | None] DateTime(timezone=True) nullable=True). __table_args__ com Index("ix_memories_vector_hnsw", "vector", postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"vector": "vector_cosine_ops"}), Index("ix_memories_user_created", "user_id", "created_at"), Index("ix_memories_tags_gin", "tags", postgresql_using="gin")
- [x] 1.2 Atualizar `app/models/__init__.py` para importar Memory de `app.models.memory` e adicioná-lo ao `__all__` (em ordem alfabética entre GraphCache e User)

## Tarefa 2: Migração Alembic

- [x] 2.1 Criar `alembic/versions/003_add_memories.py` com revision `003_memories`, down_revision `002_embeddings`: criar tabela `memories` com colunas id (Uuid PK default gen_random_uuid()), user_id (Uuid FK users.id CASCADE), content (Text not null), tags (ARRAY(String) not null server_default ARRAY[]::varchar[]), vector (Text placeholder para pgvector), created_at (DateTime timezone not null), last_accessed_at (DateTime timezone nullable). Criar índice B-tree `ix_memories_user_created` em (user_id, created_at) via op.create_index. Criar índice GIN `ix_memories_tags_gin` via op.execute com SQL direto. Criar índice HNSW `ix_memories_vector_hnsw` via op.execute com SQL direto `CREATE INDEX ix_memories_vector_hnsw ON memories USING hnsw (vector vector_cosine_ops) WITH (m = 16, ef_construction = 64)`. NÃO recriar extensão vector (já existe na migration 002). Implementar downgrade() que remove os 3 índices e a tabela memories

## Tarefa 3: Serviço de Memória

- [x] 3.1 Criar `app/services/memory.py` com constantes `_RECALL_DISTANCE_THRESHOLD = 0.5`, `_RECALL_LIMIT_DEFAULT = 5`, `_RECALL_LIMIT_MAX = 20`. Importar `generate_embedding` de `app.services.embeddings` (reutilizar singleton, NÃO criar outro). Importar `Memory` de `app.models.memory`, `select` e `update` de `sqlalchemy`, `AsyncSession` de `sqlalchemy.ext.asyncio`, `datetime` e `UUID`
- [x] 3.2 Implementar função async `save_memory(db: AsyncSession, user_id: UUID, content: str, tags: list[str] | None = None) -> dict`: validar que content.strip() não é vazio (levantar ValueError se for); limpar tags com [t.strip() for t in (tags or []) if t.strip()]; gerar vetor via generate_embedding(content); criar Memory com user_id, content, clean_tags, vector, created_at=now; db.add + commit + refresh; retornar dict com {id (str), content, tags, created_at (isoformat)}
- [x] 3.3 Implementar função async `recall_memory(db: AsyncSession, user_id: UUID, query: str, tags: list[str] | None = None, limit: int = _RECALL_LIMIT_DEFAULT) -> list[dict]`: retornar [] se query.strip() vazio; clampar limit com min(max(limit, 1), _RECALL_LIMIT_MAX); gerar query_vector via generate_embedding(query); construir SELECT com Memory e cosine_distance; filtrar por user_id; se tags fornecidas e não vazias após limpeza, filtrar com Memory.tags.overlap(clean_tags); ordenar por distance, limitar a limit; executar query; filtrar rows com distance < _RECALL_DISTANCE_THRESHOLD; se há resultados, atualizar last_accessed_at em batch via update(Memory).where(Memory.id.in_(ids)).values(last_accessed_at=now) + commit; retornar lista de {id (str), content, tags, created_at (isoformat), relevance_score (round(1-distance, 4))}

## Tarefa 4: Ferramentas MCP save_memory e recall_memory

- [x] 4.1 Adicionar constante `TOOL_SAVE_MEMORY` em `app/routers/mcp.py` como MCPTool com name="save_memory", description fixa descrevendo salvamento de memória persistente para sessões futuras (incluindo exemplos de uso), inputSchema com content (string, required, description sobre texto da memória) e tags (array de strings, opcional, description sobre tags para filtragem)
- [x] 4.2 Adicionar constante `TOOL_RECALL_MEMORY` em `app/routers/mcp.py` como MCPTool com name="recall_memory", description fixa descrevendo recuperação de memórias via busca semântica (incluindo exemplos de uso), inputSchema com query (string, required, description sobre o que buscar), tags (array de strings, opcional, description sobre filtro OR) e limit (integer, opcional, description com padrão 5 e máximo 20)
- [x] 4.3 Implementar handler `handle_save_memory(arguments, user, db, redis, graph, searxng) -> dict` em `app/routers/mcp.py`: importar save_memory de app.services.memory; extrair content (obrigatório) e tags (opcional) dos arguments; chamar save_memory(db, user.id, content, tags) dentro de try/except ValueError que converte para HTTPException(status_code=400, detail=str(exc))
- [x] 4.4 Implementar handler `handle_recall_memory(arguments, user, db, redis, graph, searxng) -> list[dict]` em `app/routers/mcp.py`: importar recall_memory de app.services.memory; extrair query (obrigatório), tags (opcional) e limit (padrão 5, máximo 20 via min(int(...), 20)) dos arguments; chamar recall_memory(db, user.id, query, tags, limit)
- [x] 4.5 Adicionar `"save_memory": handle_save_memory` e `"recall_memory": handle_recall_memory` ao `TOOLS_REGISTRY`; adicionar `"save_memory": TOOL_SAVE_MEMORY` e `"recall_memory": TOOL_RECALL_MEMORY` ao `TOOLS_MAP`; adicionar `TOOL_SAVE_MEMORY` e `TOOL_RECALL_MEMORY` ao `ALL_TOOLS` em `app/routers/mcp.py`

## Tarefa 5: Testes de Propriedade (PBT)

- [x] 5.1 `tests/test_property_memory_vector_dim.py` — Escrever property-based test: gerar strings não vazias (min 1 char) via Hypothesis, mockar `generate_embedding` para retornar lista de 384 floats e mockar db (AsyncSession), chamar `save_memory(db, user_id, content, tags)`, verificar que `generate_embedding` foi chamado com o content exato e que o vetor passado ao construtor Memory(...) tem `len == 384`. Usar `@hyp_settings(max_examples=50, deadline=None)`. (Propriedade 1: dimensão do vetor via save_memory)
- [x] 5.2 `tests/test_property_memory_tags_cleaned.py` — Escrever property-based test: gerar listas de strings arbitrárias via Hypothesis (incluindo strings vazias, com espaços), aplicar lógica de limpeza `[t.strip() for t in tags if t.strip()]`, verificar que nenhuma tag no resultado é string vazia e que todas as tags foram stripped. (Propriedade 2: tags limpas)
- [x] 5.3 `tests/test_property_recall_threshold.py` — Escrever property-based test: gerar listas de floats entre 0.0 e 1.0 representando distâncias, aplicar filtro `distance < 0.5`, verificar que todos os resultados retornados têm `relevance_score > 0.5` onde `relevance_score = round(1 - distance, 4)`. (Propriedade 3: threshold de recall)
- [x] 5.4 `tests/test_property_recall_empty_query.py` — Escrever property-based test: gerar strings compostas apenas de whitespace (espaços, tabs, newlines, string vazia) via Hypothesis, mockar db (AsyncSession), chamar `recall_memory(db, user_id, query)`, verificar que retorna `[]` E que `db.execute` nunca foi chamado (`db.execute.assert_not_called()`). Usar `@hyp_settings(max_examples=50, deadline=None)`. (Propriedade 4: query vazia não toca o banco)
- [x] 5.5 `tests/test_property_save_memory_rejects_empty.py` — Escrever property-based test: gerar strings compostas apenas de whitespace (espaços, tabs, newlines, string vazia) via Hypothesis, mockar db (AsyncSession), chamar `save_memory(db, user_id, content)`, verificar que `ValueError` é levantado E que `db.add` nunca foi chamado (`db.add.assert_not_called()`). Usar `@hyp_settings(max_examples=50, deadline=None)`. (Propriedade 5: content vazio rejeita sem tocar o banco)

## Tarefa 6: Testes de Casos de Borda

- [x] 6.1 `tests/test_edge_cases_memory.py` — Escrever teste `test_save_memory_empty_content`: chamar save_memory com content="" e content="   " (mockando db), verificar que ValueError é levantado em ambos os casos sem operação no banco
- [x] 6.2 `tests/test_edge_cases_memory.py` — Escrever teste `test_save_memory_no_tags`: chamar save_memory com tags=None e tags=[] (mockando db e generate_embedding), verificar que memória é persistida com tags=[]
- [x] 6.3 `tests/test_edge_cases_memory.py` — Escrever teste `test_save_memory_dirty_tags`: chamar save_memory com tags=["", "a", " ", "b"] (mockando db e generate_embedding), verificar que memória é persistida com tags=["a", "b"]
- [x] 6.4 `tests/test_edge_cases_memory.py` — Escrever teste `test_recall_memory_no_results`: chamar recall_memory com query válida mas mock de db retornando resultado vazio, verificar que retorna []
- [x] 6.5 `tests/test_edge_cases_memory.py` — Escrever teste `test_recall_memory_below_threshold`: mockar db retornando rows com distance >= 0.5, verificar que recall_memory retorna [] e last_accessed_at não é atualizado
- [x] 6.6 `tests/test_edge_cases_memory.py` — Escrever teste `test_recall_memory_with_tags_filter`: mockar db e generate_embedding, chamar recall_memory com tags=["preferencia"], capturar o stmt via `db.execute.call_args[0][0]`, compilar com `stmt.compile(compile_kwargs={"literal_binds": True})` e verificar que o SQL renderizado contém o operador `&&` (PostgreSQL OP_OVERLAP), confirmando que Memory.tags.overlap() foi aplicado na query
- [x] 6.7 `tests/test_edge_cases_memory.py` — Escrever teste `test_recall_memory_limit_capped`: chamar recall_memory com limit=100, verificar que a query SQL usa limit=20
- [x] 6.8 `tests/test_edge_cases_memory.py` — Escrever teste `test_recall_memory_updates_last_accessed`: mockar db com resultados abaixo do threshold, chamar recall_memory, verificar que update(Memory).values(last_accessed_at=...) é executado para os IDs retornados
- [x] 6.9 `tests/test_edge_cases_memory.py` — Escrever teste `test_mcp_save_memory_missing_content`: POST /mcp/call com name="save_memory" sem content nos arguments, verificar resposta JSON-RPC error com código -32602
- [x] 6.10 `tests/test_edge_cases_memory.py` — Escrever teste `test_mcp_recall_memory_missing_query`: POST /mcp/call com name="recall_memory" sem query nos arguments, verificar resposta JSON-RPC error com código -32602
- [x] 6.11 `tests/test_edge_cases_memory.py` — Escrever teste `test_mcp_list_tools_returns_8`: GET /mcp, verificar que retorna 8 ferramentas incluindo save_memory e recall_memory
- [x] 6.12 `tests/test_edge_cases_memory.py` — Escrever teste `test_recall_memory_filters_by_user_id` (requisito R4.2 — segurança multi-tenant): mockar db e generate_embedding, chamar recall_memory com user_id=UUID_A, capturar stmt via `db.execute.call_args[0][0]`, compilar com `stmt.compile(compile_kwargs={"literal_binds": True})` e verificar que o SQL renderizado contém condição `memories.user_id = '<UUID_A>'`, garantindo isolamento entre usuários
