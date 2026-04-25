# Tarefas de Implementação — Lanez Fase 3: Busca Semântica

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

## Tarefa 1: Dependência e Migração

- [ ] 1.1 Adicionar `sentence-transformers==3.3.1` ao `requirements.txt` (após a linha `pgvector==0.3.0`)
- [ ] 1.2 Criar `alembic/versions/002_add_embeddings.py` com revision `002_embeddings`, down_revision `001_initial`: executar `CREATE EXTENSION IF NOT EXISTS vector`, criar tabela `embeddings` com colunas id (Uuid PK), user_id (Uuid FK users.id CASCADE), service (String 20), resource_id (String 255), content_hash (String 64), vector (Text placeholder para pgvector), updated_at (DateTime timezone nullable), UniqueConstraint em (user_id, service, resource_id) com nome `uq_embedding_user_service_resource`, índice em user_id, e índice HNSW via `op.execute()` com SQL `CREATE INDEX ix_embeddings_vector_hnsw ON embeddings USING hnsw (vector vector_cosine_ops) WITH (m = 16, ef_construction = 64)`. Implementar `downgrade()` que remove índice HNSW, índice user_id e tabela embeddings

## Tarefa 2: Modelo Embedding

- [ ] 2.1 Criar `app/models/embedding.py` com classe Embedding(Base): __tablename__ = "embeddings", colunas id (UUID PK default uuid4), user_id (UUID FK "users.id" ondelete="CASCADE" nullable=False), service (String(20) nullable=False), resource_id (String(255) nullable=False), content_hash (String(64) nullable=False), vector (Vector(384) nullable=False usando pgvector.sqlalchemy.Vector), updated_at (DateTime(timezone=True) nullable=True). __table_args__ com UniqueConstraint("user_id", "service", "resource_id", name="uq_embedding_user_service_resource") e Index("ix_embeddings_vector_hnsw", vector, postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"vector": "vector_cosine_ops"})
- [ ] 2.2 Atualizar `app/models/__init__.py` para importar Embedding de `app.models.embedding` e adicioná-lo ao `__all__`

## Tarefa 3: Serviço de Embeddings — Funções Base

- [ ] 3.1 Criar `app/services/embeddings.py` com singleton do modelo: variável global `_model: SentenceTransformer | None = None`, função `get_model()` que carrega `SentenceTransformer("all-MiniLM-L6-v2")` na primeira chamada e retorna a instância singleton, função `generate_embedding(text: str) -> list[float]` que chama `get_model().encode(text).tolist()`
- [ ] 3.2 Implementar função `extract_text(service: str, data: dict) -> str` em `app/services/embeddings.py`: para "calendar" extrair subject + body.content[:500] + nomes dos attendees; para "mail" extrair subject + from.emailAddress.name + bodyPreview; para "onenote" extrair title + contentUrl; para "onedrive" extrair name + description. Concatenar campos com " | " usando filter(None, parts). Retornar string vazia para serviço desconhecido. Nunca levantar exceção
- [ ] 3.3 Implementar função `chunk_text(text: str, max_chars: int = 1200) -> list[str]` em `app/services/embeddings.py`: dividir texto por `\n\n`, agrupar parágrafos em chunks respeitando max_chars, retornar `[text[:max_chars]]` se não houver parágrafos ou texto vazio. Sempre retornar pelo menos 1 chunk

## Tarefa 4: Serviço de Embeddings — Ingestão e Busca

- [ ] 4.1 Implementar função async `ingest_item(db: AsyncSession, user_id: UUID, service: str, resource_id: str, text: str) -> bool` em `app/services/embeddings.py`: retornar False se texto vazio; calcular content_hash via SHA-256; buscar embedding existente por (user_id, service, resource_id); se existe com mesmo hash retornar False (skip); se existe com hash diferente atualizar vector, content_hash, updated_at; se não existe inserir novo Embedding; commit e retornar True
- [ ] 4.2 Implementar função async `ingest_graph_data(db: AsyncSession, user_id: UUID, service: str, resource_id: str, data: dict) -> None` em `app/services/embeddings.py`: chamar extract_text para obter texto; se vazio retornar; chamar chunk_text; se 1 chunk chamar ingest_item com resource_id original; se múltiplos chunks chamar ingest_item para cada com resource_id `"{resource_id}__chunk_{i}"`
- [ ] 4.3 Implementar função async `semantic_search(db: AsyncSession, user_id: UUID, query: str, limit: int = 10, services: list[str] | None = None) -> list[dict]` em `app/services/embeddings.py`: gerar embedding da query via generate_embedding; construir SELECT com Embedding e cosine_distance; filtrar por user_id; se services fornecido filtrar por Embedding.service.in_(services); ordenar por distance; limitar a limit; executar query; retornar lista de {service, resource_id, relevance_score} filtrando distance < 0.5 onde relevance_score = round(1 - distance, 4)

## Tarefa 5: Modificar process_notification (webhook.py)

- [ ] 5.1 Alterar tipo de retorno de `process_notification` em `app/services/webhook.py` de `bool` para `tuple[uuid.UUID, ServiceType] | None`: onde retornava `return False` (subscrição não encontrada, resource desconhecido) agora retornar `return None`; onde retornava `return True` (após invalidar cache) agora retornar `return user_id, service_type`. Manter HTTPException(403) para clientState inválido sem alteração. Atualizar docstring e type hints

## Tarefa 6: Modificar Router Webhooks (re-embedding background)

- [ ] 6.1 Adicionar função async `_reingest_background(user_id: uuid.UUID, service_type: ServiceType)` em `app/routers/webhooks.py`: criar nova AsyncSessionLocal; instanciar GraphService; obter redis via get_redis() (função síncrona); chamar graph_svc.fetch_data(user_id, service_type, db, redis); iterar sobre items em response.data.get("value", []); para cada item com id chamar ingest_graph_data(db, user_id, service_type.value, resource_id, item); logar erros com [token=REDACTED] sem propagar; fechar GraphService no finally
- [ ] 6.2 Modificar endpoint `receive_graph_notification` em `app/routers/webhooks.py`: adicionar parâmetro `background_tasks: BackgroundTasks`; após `process_notification` retornar resultado, verificar se resultado não é None; se não None, extrair (user_id, service_type) e chamar `background_tasks.add_task(_reingest_background, user_id, service_type)`. Adicionar imports necessários (BackgroundTasks, uuid, ingest_graph_data, AsyncSessionLocal, get_redis, GraphService, ServiceType)

## Tarefa 7: Adicionar Ferramenta semantic_search ao MCP

- [ ] 7.1 Adicionar constante `TOOL_SEMANTIC_SEARCH` em `app/routers/mcp.py` como MCPTool com name="semantic_search", description fixa (string hardcoded descrevendo busca por significado em todos os serviços), inputSchema com query (string, required), services (array de strings enum calendar/mail/onenote/onedrive, opcional) e limit (integer, opcional, padrão 10, máximo 20)
- [ ] 7.2 Implementar handler `handle_semantic_search(arguments, user, db, redis, graph, searxng)` em `app/routers/mcp.py`: importar semantic_search de app.services.embeddings; extrair query (obrigatório), services (opcional) e limit (padrão 10, máximo 20 via min()); chamar semantic_search(db, user.id, query, limit, services); retornar resultado
- [ ] 7.3 Adicionar `handle_semantic_search` ao `TOOLS_REGISTRY`, `TOOL_SEMANTIC_SEARCH` ao `TOOLS_MAP`, e `TOOL_SEMANTIC_SEARCH` ao `ALL_TOOLS` em `app/routers/mcp.py`

## Tarefa 8: Precarregar Modelo no Startup

- [ ] 8.1 Modificar `app/main.py`: adicionar import `from app.services.embeddings import get_model`; no lifespan, após `Base.metadata.create_all` e antes de `renewal_task`, chamar `get_model()` e logar `"Modelo de embeddings carregado"`

## Tarefa 9: Testes de Propriedade

- [ ] 9.1 Escrever property-based test para dimensão do vetor: gerar strings aleatórias não vazias (min 1 char), chamar generate_embedding, verificar que retorna lista de exatamente 384 floats (Propriedade 1)
- [ ] 9.2 Escrever property-based test para content_hash SHA-256: gerar strings aleatórias, calcular SHA-256, verificar que resultado tem exatamente 64 caracteres e todos são hexadecimais (Propriedade 2)
- [ ] 9.3 Escrever property-based test para chunk_text: gerar textos aleatórios não vazios e valores de max_chars positivos (min 10), chamar chunk_text, verificar que retorna lista com pelo menos 1 elemento (Propriedade 3)
- [ ] 9.4 Escrever property-based test para deduplicação: criar embedding no banco com texto aleatório, chamar ingest_item novamente com mesmo texto, verificar que retorna False na segunda chamada (Propriedade 4)
- [ ] 9.5 Escrever property-based test para threshold da busca semântica: ingerir textos aleatórios, buscar com query aleatória, verificar que todos os resultados retornados têm relevance_score > 0.5 (Propriedade 5)
- [ ] 9.6 Escrever property-based test para retorno de process_notification: gerar notificações com clientState válido e subscription_id existente/inexistente, verificar que retorno é tuple (UUID, ServiceType) ou None, nunca bool (Propriedade 6)
- [ ] 9.7 Escrever property-based test para extract_text: gerar dicts aleatórios como data e services aleatórios entre os 4 válidos, verificar que extract_text sempre retorna string sem levantar exceção (Propriedade 8)

## Tarefa 10: Testes de Casos de Borda

- [ ] 10.1 Escrever teste para texto vazio em ingest_item: chamar com texto vazio e texto só com espaços, verificar que retorna False sem operação no banco (Caso de Borda 1)
- [ ] 10.2 Escrever teste para texto longo com múltiplos chunks: criar texto de 5000 chars com parágrafos, chamar chunk_text, verificar que retorna múltiplos chunks (Caso de Borda 2)
- [ ] 10.3 Escrever teste para texto sem parágrafos: criar texto contínuo sem `\n\n`, chamar chunk_text, verificar que retorna `[text[:max_chars]]` (Caso de Borda 3)
- [ ] 10.4 Escrever teste para busca semântica sem embeddings: chamar semantic_search com user_id sem embeddings no banco, verificar que retorna lista vazia (Caso de Borda 4)
- [ ] 10.5 Escrever teste para busca semântica com serviço inexistente: chamar semantic_search com services=["inexistente"], verificar que retorna lista vazia (Caso de Borda 5)
- [ ] 10.6 Escrever teste para erro no re-embedding background: mock GraphService.fetch_data levantando HTTPException(401), chamar _reingest_background, verificar que erro é logado e função encerra sem propagar exceção (Caso de Borda 6)
- [ ] 10.7 Escrever teste para content_hash igual (skip): ingerir item, chamar ingest_item novamente com mesmo texto, verificar que retorna False (Caso de Borda 8)
- [ ] 10.8 Escrever teste para parâmetro query ausente em semantic_search via MCP: POST /mcp/call com name="semantic_search" sem query nos arguments, verificar resposta JSON-RPC error com código -32602 (Caso de Borda 9)
- [ ] 10.9 Escrever teste para limit excedendo máximo: chamar handle_semantic_search com limit=100, verificar que query usa limit=20 (Caso de Borda 10)
- [ ] 10.10 Escrever teste para lista de ferramentas MCP com 6 itens: GET /mcp, verificar que retorna 6 ferramentas incluindo semantic_search (Propriedade 7)
