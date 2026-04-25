# Documento de Requisitos — Lanez Fase 3: Busca Semântica

## Introdução

A Fase 3 do Lanez implementa busca semântica (por significado) em todos os serviços do Microsoft 365 simultaneamente — calendário, emails, OneNote e OneDrive. A ferramenta `semantic_search` é exposta como 6ª ferramenta MCP, permitindo que AI assistants encontrem informações relevantes sem depender de palavras-chave exatas. A implementação usa pgvector (já no stack) com o modelo local `all-MiniLM-L6-v2` via `sentence-transformers`, embeddings armazenados em PostgreSQL com índice HNSW, e re-embedding automático via webhooks em background. Esta fase reutiliza toda a infraestrutura das Fases 1 e 2 (autenticação JWT, GraphService, cache Redis, MCP server).

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Servidor_MCP**: Módulo responsável por implementar o protocolo MCP via JSON-RPC 2.0
- **Cliente_MCP**: AI assistant (Claude Desktop, Cursor) que consome as ferramentas MCP
- **Cliente_Graph**: Módulo GraphService responsável por consumir a Microsoft Graph API
- **Serviço_Embeddings**: Módulo responsável por gerar, armazenar e buscar embeddings vetoriais
- **Modelo_Embedding**: Instância singleton do SentenceTransformer all-MiniLM-L6-v2
- **Embedding**: Representação vetorial de 384 dimensões de um trecho de texto
- **Cosine_Distance**: Métrica de distância entre vetores — 0 = idênticos, 1 = ortogonais
- **HNSW**: Hierarchical Navigable Small World — algoritmo de índice para busca vetorial aproximada
- **content_hash**: Hash SHA-256 do texto usado para deduplicação de embeddings
- **Chunk**: Fragmento de texto dividido por parágrafo, limitado a ~1200 caracteres
- **Re-embedding**: Processo de atualizar embeddings quando dados do Microsoft 365 mudam
- **pgvector**: Extensão PostgreSQL para armazenamento e busca de vetores
- **Graph_API**: Microsoft Graph API v1.0

## Requisitos

### Requisito 1: Modelo de Dados Embedding

**User Story:** Como desenvolvedor, quero um modelo de dados para armazenar embeddings vetoriais, para que textos do Microsoft 365 possam ser indexados e buscados por significado.

#### Critérios de Aceitação

1. THE Sistema SHALL criar a tabela `embeddings` com as colunas: id (UUID PK), user_id (UUID FK users.id ON DELETE CASCADE), service (String 20), resource_id (String 255), content_hash (String 64), vector (Vector 384 pgvector), updated_at (DateTime timezone nullable)
2. THE Sistema SHALL criar uma UniqueConstraint em (user_id, service, resource_id) com nome `uq_embedding_user_service_resource`
3. THE Sistema SHALL criar um índice HNSW na coluna vector com operador `vector_cosine_ops` e parâmetros m=16, ef_construction=64
4. WHEN um registro User é deletado, THE Sistema SHALL deletar automaticamente todos os embeddings associados via CASCADE
5. THE Sistema SHALL importar o modelo Embedding em `app/models/__init__.py` para que `Base.metadata.create_all` o inclua

### Requisito 2: Migração Alembic para Embeddings

**User Story:** Como desenvolvedor, quero uma migração Alembic que crie a tabela embeddings com pgvector, para que o schema do banco seja versionado e reproduzível.

#### Critérios de Aceitação

1. THE Sistema SHALL criar a migração `alembic/versions/002_add_embeddings.py` com revision `002_embeddings` e down_revision `001_initial`
2. THE migração SHALL executar `CREATE EXTENSION IF NOT EXISTS vector` antes de criar a tabela
3. THE migração SHALL criar a tabela `embeddings` com todas as colunas, constraints e foreign keys definidas no modelo
4. THE migração SHALL criar o índice HNSW via `op.execute()` com SQL direto, pois o tipo vector não tem representação nativa no Alembic
5. THE migração SHALL implementar `downgrade()` que remove o índice HNSW, o índice de user_id e a tabela embeddings

### Requisito 3: Singleton do Modelo de Embedding

**User Story:** Como operador do sistema, quero que o modelo de embedding seja carregado uma única vez no startup, para que a aplicação não gaste ~2s e ~300MB a cada requisição.

#### Critérios de Aceitação

1. THE Serviço_Embeddings SHALL expor uma função `get_model()` que retorna uma instância singleton de `SentenceTransformer("all-MiniLM-L6-v2")`
2. WHEN `get_model()` é chamado pela primeira vez, THE Serviço_Embeddings SHALL carregar o modelo e armazená-lo em variável global
3. WHEN `get_model()` é chamado subsequentemente, THE Serviço_Embeddings SHALL retornar a mesma instância sem recarregar
4. THE Sistema SHALL chamar `get_model()` no lifespan startup de `app/main.py` para forçar o carregamento antecipado do modelo
5. THE Serviço_Embeddings SHALL expor uma função `generate_embedding(text)` que retorna uma lista de exatamente 384 floats

### Requisito 4: Extração de Texto por Serviço

**User Story:** Como desenvolvedor, quero extrair texto relevante de itens da Graph API por tipo de serviço, para que os embeddings representem o conteúdo semântico de cada item.

#### Critérios de Aceitação

1. THE Serviço_Embeddings SHALL expor uma função `extract_text(service, data)` que retorna uma string com texto relevante concatenado por " | "
2. WHEN service é "calendar", THE função SHALL extrair subject, body.content (limitado a 500 chars) e nomes dos attendees
3. WHEN service é "mail", THE função SHALL extrair subject, from.emailAddress.name e bodyPreview
4. WHEN service é "onenote", THE função SHALL extrair title e contentUrl
5. WHEN service é "onedrive", THE função SHALL extrair name e description
6. IF nenhum campo relevante for encontrado, THEN THE função SHALL retornar string vazia
7. THE função `extract_text` SHALL NEVER levantar exceção — campos ausentes devem retornar string vazia

### Requisito 5: Chunking de Texto

**User Story:** Como desenvolvedor, quero dividir textos longos em chunks menores, para que embeddings representem trechos semanticamente coesos dentro do limite do modelo.

#### Critérios de Aceitação

1. THE Serviço_Embeddings SHALL expor uma função `chunk_text(text, max_chars=1200)` que divide texto por parágrafos (`\n\n`)
2. FOR ALL textos não vazios, THE função SHALL retornar uma lista com pelo menos 1 chunk
3. THE função SHALL preservar parágrafos inteiros — nunca cortar uma frase no meio
4. IF o texto não contém parágrafos (`\n\n`), THEN THE função SHALL retornar `[text[:max_chars]]`
5. WHEN um chunk excede max_chars, THE função SHALL iniciar um novo chunk com o parágrafo atual

### Requisito 6: Ingestão de Embeddings com Deduplicação

**User Story:** Como desenvolvedor, quero ingerir embeddings com deduplicação por content_hash, para que o sistema não re-processe textos que não mudaram.

#### Critérios de Aceitação

1. THE Serviço_Embeddings SHALL expor uma função `ingest_item(db, user_id, service, resource_id, text)` que gera e upserta o embedding
2. IF o texto for vazio, THEN THE função SHALL retornar False sem operação no banco
3. THE função SHALL calcular o content_hash como `hashlib.sha256(text.encode()).hexdigest()`
4. IF um embedding já existe para (user_id, service, resource_id) com o mesmo content_hash, THEN THE função SHALL retornar False sem atualizar (deduplicação)
5. IF um embedding já existe com content_hash diferente, THEN THE função SHALL atualizar vector, content_hash e updated_at
6. IF nenhum embedding existe, THEN THE função SHALL inserir um novo registro
7. THE Serviço_Embeddings SHALL expor uma função `ingest_graph_data(db, user_id, service, resource_id, data)` que extrai texto, faz chunking e ingere embeddings — usando resource_id original para 1 chunk ou `"{resource_id}__chunk_{i}"` para múltiplos chunks

### Requisito 7: Busca Semântica

**User Story:** Como usuário via AI assistant, quero buscar informações por significado em todos os serviços do Microsoft 365 simultaneamente, para que o assistant encontre resultados relevantes mesmo sem palavras-chave exatas.

#### Critérios de Aceitação

1. THE Serviço_Embeddings SHALL expor uma função `semantic_search(db, user_id, query, limit=10, services=None)` que busca por cosine distance
2. THE função SHALL gerar o embedding da query via `generate_embedding(query)` e buscar os embeddings mais próximos no banco
3. THE função SHALL filtrar resultados por `user_id` — um usuário nunca vê embeddings de outro
4. IF `services` for fornecido, THEN THE função SHALL filtrar apenas pelos serviços especificados
5. THE função SHALL descartar resultados com cosine_distance >= 0.5 (relevance_score <= 0.5)
6. THE função SHALL retornar lista de `{service, resource_id, relevance_score}` ordenada por relevance_score decrescente
7. THE função SHALL limitar resultados a `limit` (máximo 20)

### Requisito 8: Ferramenta MCP semantic_search

**User Story:** Como cliente MCP, quero uma ferramenta de busca semântica, para que eu possa encontrar informações em todos os serviços do Microsoft 365 por significado.

#### Critérios de Aceitação

1. THE Servidor_MCP SHALL expor uma 6ª ferramenta chamada `semantic_search` com description fixa (string hardcoded)
2. THE ferramenta SHALL aceitar parâmetro obrigatório `query` (string) e parâmetros opcionais `services` (array de strings) e `limit` (integer)
3. WHEN a ferramenta é chamada, THE handler SHALL invocar `semantic_search` do Serviço_Embeddings com os parâmetros fornecidos
4. THE handler SHALL limitar `limit` a no máximo 20 (`min(limit, 20)`)
5. IF o parâmetro `query` estiver ausente, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602
6. THE ferramenta SHALL ser adicionada ao `TOOLS_REGISTRY`, `TOOLS_MAP` e `ALL_TOOLS`
7. WHEN GET /mcp é chamado, THE Servidor_MCP SHALL retornar lista com 6 ferramentas incluindo `semantic_search`

### Requisito 9: Retorno Tuple de process_notification

**User Story:** Como desenvolvedor, quero que `process_notification` retorne informações do usuário e serviço, para que o router possa agendar re-embedding em background.

#### Critérios de Aceitação

1. THE método `process_notification` em `app/services/webhook.py` SHALL retornar `tuple[uuid.UUID, ServiceType] | None` em vez de `bool`
2. WHEN a notificação é processada com sucesso (cache invalidado), THE método SHALL retornar `(user_id, service_type)`
3. WHEN a subscrição não é encontrada no banco, THE método SHALL retornar `None`
4. WHEN o resource não pode ser mapeado para ServiceType, THE método SHALL retornar `None`
5. IF o clientState for inválido, THEN THE método SHALL continuar levantando HTTPException(403) — sem mudança

### Requisito 10: Re-embedding via Webhook em Background

**User Story:** Como operador do sistema, quero que embeddings sejam atualizados automaticamente quando dados do Microsoft 365 mudam, para que a busca semântica reflita o estado atual dos dados.

#### Critérios de Aceitação

1. THE router `app/routers/webhooks.py` SHALL aceitar `BackgroundTasks` como parâmetro no endpoint POST /webhooks/graph
2. WHEN `process_notification` retorna `(user_id, service_type)`, THE router SHALL agendar `_reingest_background(user_id, service_type)` via `background_tasks.add_task()`
3. THE função `_reingest_background` SHALL criar uma nova `AsyncSessionLocal` (não compartilhar sessão do request)
4. THE função `_reingest_background` SHALL usar `get_redis()` diretamente (função síncrona que retorna o client Redis global)
5. THE função `_reingest_background` SHALL buscar dados frescos via `GraphService.fetch_data`, extrair texto e ingerir embeddings para cada item
6. IF ocorrer erro durante re-embedding, THEN THE função SHALL logar o erro e encerrar silenciosamente — nunca propagar exceção
7. THE endpoint POST /webhooks/graph SHALL continuar retornando HTTP 202 imediatamente, sem aguardar o re-embedding

### Requisito 11: Dependência sentence-transformers

**User Story:** Como desenvolvedor, quero que a dependência sentence-transformers esteja declarada no requirements.txt, para que o modelo de embedding possa ser carregado.

#### Critérios de Aceitação

1. THE Sistema SHALL adicionar `sentence-transformers==3.3.1` ao arquivo `requirements.txt`
