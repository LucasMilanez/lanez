# Documento de Requisitos — Lanez Fase 4: Memória Persistente

## Introdução

A Fase 4 do Lanez implementa memória persistente para o AI assistant. O usuário (ou o próprio AI, via MCP) salva decisões, projetos em andamento, preferências e fatos importantes. Em sessões futuras, o AI recupera memórias relevantes para a conversa atual usando busca semântica. Diferente dos embeddings da Fase 3 (derivados automaticamente do Microsoft 365 via webhook), memórias são input explícito e intencional — cada `save_memory` é sempre um INSERT novo, sem deduplicação. A implementação reutiliza o modelo `all-MiniLM-L6-v2` singleton da Fase 3 via `generate_embedding()`, armazena texto completo + tags + vetor na tabela `memories`, e expõe duas novas ferramentas MCP (`save_memory` e `recall_memory`), totalizando 8 ferramentas.

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Servidor_MCP**: Módulo responsável por implementar o protocolo MCP via JSON-RPC 2.0
- **Cliente_MCP**: AI assistant (Claude Desktop, Cursor) que consome as ferramentas MCP
- **Serviço_Memória**: Módulo `app/services/memory.py` responsável por salvar e recuperar memórias
- **Serviço_Embeddings**: Módulo `app/services/embeddings.py` existente da Fase 3 (singleton do modelo, `generate_embedding`)
- **Memória**: Registro persistente contendo texto, tags e vetor de embedding — input explícito do usuário ou AI
- **Embedding**: Representação vetorial de 384 dimensões gerada pelo modelo all-MiniLM-L6-v2
- **Cosine_Distance**: Métrica de distância entre vetores — 0 = idênticos, 1 = ortogonais
- **HNSW**: Hierarchical Navigable Small World — algoritmo de índice para busca vetorial aproximada
- **GIN**: Generalized Inverted Index — índice PostgreSQL para arrays e busca por sobreposição
- **Tags**: Array nativo PostgreSQL (`ARRAY(String)`) associado a cada memória para filtragem
- **Overlap**: Operador `&&` do PostgreSQL — verdadeiro se dois arrays têm pelo menos um elemento em comum (filtro OR)
- **last_accessed_at**: Timestamp atualizado quando uma memória é retornada por `recall_memory`
- **pgvector**: Extensão PostgreSQL para armazenamento e busca de vetores

## Requisitos

### Requisito 1: Modelo de Dados Memory

**User Story:** Como desenvolvedor, quero um modelo de dados para armazenar memórias persistentes com texto, tags e vetor, para que o AI assistant possa salvar e recuperar contexto entre sessões.

#### Critérios de Aceitação

1. THE Sistema SHALL criar a tabela `memories` com as colunas: id (UUID PK default uuid4), user_id (UUID FK users.id ON DELETE CASCADE), content (Text não nulo), tags (ARRAY(String) não nulo default lista vazia), vector (Vector(384) pgvector não nulo), created_at (DateTime timezone não nulo), last_accessed_at (DateTime timezone nullable)
2. THE Sistema SHALL criar um índice HNSW na coluna vector com operador `vector_cosine_ops` e parâmetros m=16, ef_construction=64
3. THE Sistema SHALL criar um índice GIN na coluna tags para filtragem eficiente por sobreposição
4. THE Sistema SHALL criar um índice B-tree composto em (user_id, created_at) para listagens cronológicas
5. WHEN um registro User é deletado, THE Sistema SHALL deletar automaticamente todas as memórias associadas via CASCADE
6. THE Sistema SHALL usar `ARRAY(String)` nativo do PostgreSQL para tags — não JSON ou JSONB
7. THE Sistema SHALL importar o modelo Memory em `app/models/__init__.py` e adicioná-lo ao `__all__`

### Requisito 2: Migração Alembic para Memories

**User Story:** Como desenvolvedor, quero uma migração Alembic que crie a tabela memories com pgvector e índices, para que o schema do banco seja versionado e reproduzível.

#### Critérios de Aceitação

1. THE Sistema SHALL criar a migração `alembic/versions/003_add_memories.py` com revision `003_memories` e down_revision `002_embeddings`
2. THE migração SHALL criar a tabela `memories` com todas as colunas, constraints e foreign keys definidas no modelo
3. THE migração SHALL criar o índice HNSW via `op.execute()` com SQL direto: `CREATE INDEX ix_memories_vector_hnsw ON memories USING hnsw (vector vector_cosine_ops) WITH (m = 16, ef_construction = 64)`
4. THE migração SHALL criar o índice GIN via `op.execute()` com SQL direto: `CREATE INDEX ix_memories_tags_gin ON memories USING gin(tags)`
5. THE migração SHALL criar o índice B-tree composto `ix_memories_user_created` em (user_id, created_at)
6. THE migração SHALL usar `server_default=sa.text("ARRAY[]::varchar[]")` para o default de tags
7. THE migração SHALL implementar `downgrade()` que remove os 3 índices e a tabela memories

### Requisito 3: Serviço save_memory

**User Story:** Como usuário via AI assistant, quero salvar memórias persistentes com texto e tags opcionais, para que decisões, preferências e fatos importantes sejam lembrados em sessões futuras.

#### Critérios de Aceitação

1. THE Serviço_Memória SHALL expor uma função async `save_memory(db, user_id, content, tags)` que persiste uma nova memória
2. WHEN `save_memory` é chamado, THE Serviço_Memória SHALL sempre executar INSERT — nunca atualizar memórias existentes
3. THE Serviço_Memória SHALL gerar o vetor de embedding via `generate_embedding(content)` importado de `app.services.embeddings` — sem criar outro singleton
4. THE Serviço_Memória SHALL limpar tags com `.strip()` e descartar strings vazias antes de persistir
5. IF content for vazio ou contiver apenas espaços em branco, THEN THE Serviço_Memória SHALL levantar `ValueError` sem executar operação no banco
6. THE Serviço_Memória SHALL retornar dict com id, content, tags e created_at após persistir a memória
7. WHEN tags não são fornecidas (None ou lista vazia), THE Serviço_Memória SHALL persistir a memória com `tags=[]`

### Requisito 4: Serviço recall_memory

**User Story:** Como usuário via AI assistant, quero recuperar memórias relevantes por busca semântica com filtro opcional de tags, para que o assistant tenha contexto sobre decisões e preferências passadas.

#### Critérios de Aceitação

1. THE Serviço_Memória SHALL expor uma função async `recall_memory(db, user_id, query, tags, limit)` que recupera memórias por busca semântica
2. THE Serviço_Memória SHALL filtrar resultados por user_id — um usuário nunca vê memórias de outro
3. THE Serviço_Memória SHALL descartar resultados com cosine_distance >= 0.5 (relevance_score <= 0.5)
4. IF tags forem fornecidas, THEN THE Serviço_Memória SHALL filtrar memórias usando `overlap()` (operador `&&`) — memória deve conter PELO MENOS UMA tag da lista (filtro OR)
5. THE Serviço_Memória SHALL usar limit padrão 5 e limitar ao máximo 20 (`min(max(limit, 1), 20)`)
6. IF query for vazia ou contiver apenas espaços em branco, THEN THE Serviço_Memória SHALL retornar lista vazia sem executar busca no banco
7. WHEN resultados são retornados, THE Serviço_Memória SHALL atualizar `last_accessed_at` dos resultados via batch `update().where().values()` — não em loop individual
8. THE Serviço_Memória SHALL retornar lista de dicts com id, content, tags, created_at e relevance_score ordenada por relevance_score decrescente

### Requisito 5: Ferramenta MCP save_memory

**User Story:** Como cliente MCP, quero uma ferramenta para salvar memórias persistentes, para que o AI assistant possa registrar decisões e preferências do usuário.

#### Critérios de Aceitação

1. THE Servidor_MCP SHALL expor uma 7ª ferramenta chamada `save_memory` com description fixa (string hardcoded)
2. THE ferramenta SHALL aceitar parâmetro obrigatório `content` (string) e parâmetro opcional `tags` (array de strings)
3. WHEN a ferramenta é chamada, THE handler SHALL invocar `save_memory` do Serviço_Memória com os parâmetros fornecidos
4. IF `save_memory` levantar `ValueError` (content vazio), THEN THE handler SHALL converter para `HTTPException(400)` que o dispatcher converte em `jsonrpc_domain_error`
5. IF o parâmetro `content` estiver ausente, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602
6. THE ferramenta SHALL ser adicionada ao `TOOLS_REGISTRY`, `TOOLS_MAP` e `ALL_TOOLS`

### Requisito 6: Ferramenta MCP recall_memory

**User Story:** Como cliente MCP, quero uma ferramenta para recuperar memórias relevantes por busca semântica, para que o AI assistant tenha contexto sobre sessões anteriores.

#### Critérios de Aceitação

1. THE Servidor_MCP SHALL expor uma 8ª ferramenta chamada `recall_memory` com description fixa (string hardcoded)
2. THE ferramenta SHALL aceitar parâmetro obrigatório `query` (string) e parâmetros opcionais `tags` (array de strings) e `limit` (integer)
3. WHEN a ferramenta é chamada, THE handler SHALL invocar `recall_memory` do Serviço_Memória com os parâmetros fornecidos
4. THE handler SHALL limitar `limit` a no máximo 20 (`min(int(arguments.get("limit", 5)), 20)`)
5. IF o parâmetro `query` estiver ausente, THEN THE Servidor_MCP SHALL retornar erro JSON-RPC -32602
6. THE ferramenta SHALL ser adicionada ao `TOOLS_REGISTRY`, `TOOLS_MAP` e `ALL_TOOLS`
7. WHEN GET /mcp é chamado, THE Servidor_MCP SHALL retornar lista com 8 ferramentas incluindo `save_memory` e `recall_memory`
