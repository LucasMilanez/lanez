# Lanez — Briefing Fase 4.5 para KIRO

## Contexto

As Fases 1, 2, 3 e 4 estão entregues, com 121/121 testes verdes. Antes de iniciar a Fase 5, é necessário sanear dívidas técnicas acumuladas que **não trancam funcionalidade hoje** mas **viram bugs reais em deploy contra Postgres**, em CI ao longo do tempo, ou bloqueiam composição transacional em fases futuras.

Esta fase é **exclusivamente saneamento técnico**. Não há feature nova, não há tabela nova, não há tool MCP nova. O escopo são 5 issues bem delimitados, cada um com causa, correção e validação claras.

---

## O que NÃO entra nesta fase (não tocar)

- Adicionar features ou endpoints novos
- Renomear arquivos, mover diretórios, refatorar para padrões diferentes
- Mexer em `app/routers/auth.py`, `app/services/graph.py`, `app/services/cache.py`, `app/services/searxng.py`, `app/services/webhook.py`
- Mexer em testes que não estejam diretamente relacionados aos 5 issues abaixo
- Adicionar `from __future__ import annotations` em arquivos onde já está faltando
- Modificar `app/config.py` ou variáveis de ambiente
- Adicionar logs ou observabilidade nova

Se aparecer dúvida de escopo, **prefira não tocar**. O briefing lista exaustivamente o que deve mudar.

---

## Issues a resolver (todos obrigatórios)

### Issue C1 — Coluna `vector` deve ser `Vector(384)`, não `sa.Text()`

**Severidade:** Crítico — bloqueia `alembic upgrade head` contra Postgres real.

**Arquivos:**
- `alembic/versions/002_add_embeddings.py`
- `alembic/versions/003_add_memories.py`

**Estado atual (errado):**
```python
sa.Column("vector", sa.Text(), nullable=False),
```

E mais embaixo:
```python
op.execute(
    "CREATE INDEX ix_embeddings_vector_hnsw ON embeddings "
    "USING hnsw (vector vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)"
)
```

**Por que está errado:** Em Postgres real, `sa.Text()` cria a coluna com tipo `text`. O `CREATE INDEX USING hnsw (vector vector_cosine_ops)` falha com `data type text has no default operator class for access method "hnsw"`. O índice só funciona se a coluna for tipo `vector(N)` do pgvector.

**Por que passou nos testes:** Os testes mockam `AsyncSession`. A migration nunca é executada contra um banco real.

**Correção:**

No topo de `002_add_embeddings.py` e `003_add_memories.py`, adicionar:
```python
from pgvector.sqlalchemy import Vector
```

Trocar a coluna:
```python
sa.Column("vector", Vector(384), nullable=False),
```

O `op.execute("CREATE INDEX ... USING hnsw ...")` permanece igual (raw SQL, já correto).

**O que NÃO mudar:** O modelo SQLAlchemy em `app/models/embedding.py` e `app/models/memory.py` já usa `Vector(384)` corretamente. Não tocar.

**Validação:** A suíte completa deve continuar passando após a mudança. Se quiser validar end-to-end (opcional, recomendado): subir Postgres com pgvector via Docker e rodar `alembic upgrade head`.

---

### Issue A1 — Property test `recall_threshold` flaky por arredondamento

**Severidade:** Alto — vai aparecer aleatoriamente em CI ao longo do tempo.

**Arquivo:** `tests/test_property_recall_threshold.py`

**Estado atual (problemático):**
```python
@given(distances=lists(floats(min_value=0.0, max_value=1.0, ...), ...))
@hyp_settings(max_examples=50, deadline=None)
def test_recall_threshold_filters_correctly(distances: list[float]) -> None:
    filtered = [d for d in distances if d < 0.5]
    scores = [round(1 - d, 4) for d in filtered]
    assert all(score > 0.5 for score in scores), ...
```

**Por que está errado:** Quando `distance = 0.49999...`, `1 - distance = 0.50001...`, e `round(0.50001, 4)` pode retornar `0.5` exatamente (banker's rounding em Python). Nesse caso, o assert `score > 0.5` falha. O Hypothesis vai eventualmente encontrar essa seed e o teste vira flaky.

**Causa estrutural:** O filtro real do `recall_memory` (`distance < 0.5`) admite `distance = 0.49999`, mas o `relevance_score = round(1 - distance, 4)` arredonda para `0.5`. Logo, a propriedade declarada `score > 0.5` é mais forte do que o filtro real consegue garantir. O assert correto é `score >= 0.5`.

**Correção:** Trocar a linha do assert para:
```python
assert all(score >= 0.5 for score in scores), (
    f"Encontrado relevance_score < 0.5: {scores}. Distâncias filtradas: {filtered}"
)
```

**O que NÃO mudar:** O serviço `recall_memory` em `app/services/memory.py` permanece com `distance < _RECALL_DISTANCE_THRESHOLD` e `round(1 - distance, 4)`. Não tocar no serviço.

**Validação:** Rodar o teste com várias seeds (`pytest tests/test_property_recall_threshold.py --hypothesis-seed=0`, `--hypothesis-seed=1`, ..., `--hypothesis-seed=20`) e confirmar que passa em todas.

---

### Issue A2 — Embeddings órfãos em chunking dinâmico

**Severidade:** Alto — busca semântica retorna trechos desatualizados quando o conteúdo de um recurso é editado.

**Arquivo:** `app/services/embeddings.py`, função `ingest_graph_data` (linhas 182-204).

**Estado atual (errado):**
```python
async def ingest_graph_data(
    db: AsyncSession,
    user_id: UUID,
    service: str,
    resource_id: str,
    data: dict,
) -> None:
    text = extract_text(service, data)
    if not text:
        return

    chunks = chunk_text(text)
    if len(chunks) == 1:
        await ingest_item(db, user_id, service, resource_id, chunks[0])
    else:
        for i, chunk in enumerate(chunks):
            await ingest_item(db, user_id, service, f"{resource_id}__chunk_{i}", chunk)
```

**Por que está errado:** Cada `ingest_item` faz upsert por `(user_id, service, resource_id)`. Mas quando o mesmo recurso muda de tamanho entre re-ingestões (ex: email editado), o número de chunks pode mudar:

| Ingestão | Chunks | Resource IDs gravados |
|---|---|---|
| 1ª (email longo) | 3 | `abc__chunk_0`, `abc__chunk_1`, `abc__chunk_2` |
| 2ª (email editado curto) | 1 | `abc` |

Após a 2ª ingestão, `abc__chunk_0`, `abc__chunk_1` e `abc__chunk_2` ficam órfãos no banco — busca semântica vai retornar conteúdo da versão antiga.

**Correção:** No início da função (após validar `text` não vazio, antes do chunking), executar um `DELETE` que remove todas as variantes do `resource_id`:

```python
from sqlalchemy import delete, or_

from app.models.embedding import Embedding


async def ingest_graph_data(
    db: AsyncSession,
    user_id: UUID,
    service: str,
    resource_id: str,
    data: dict,
) -> None:
    text = extract_text(service, data)
    if not text:
        return

    # Remover entradas antigas do mesmo resource_id (cobrindo 1↔N chunks)
    await db.execute(
        delete(Embedding).where(
            Embedding.user_id == user_id,
            Embedding.service == service,
            or_(
                Embedding.resource_id == resource_id,
                Embedding.resource_id.like(f"{resource_id}__chunk_%"),
            ),
        )
    )

    chunks = chunk_text(text)
    if len(chunks) == 1:
        await ingest_item(db, user_id, service, resource_id, chunks[0])
    else:
        for i, chunk in enumerate(chunks):
            await ingest_item(db, user_id, service, f"{resource_id}__chunk_{i}", chunk)
```

**Importante:** Após o issue M1 (abaixo), `ingest_item` não fará mais commit. Então o `DELETE` acima vai compor naturalmente na mesma transação.

**Novo teste obrigatório:** Adicionar em `tests/test_edge_cases_embeddings.py` (arquivo já existe):

```python
@pytest.mark.asyncio
async def test_ingest_graph_data_cleans_orphan_chunks_on_resize():
    """Re-ingestão de recurso que muda de N para 1 chunk não deixa órfãos."""
    # Mock db.execute capturando todas as chamadas (DELETE + SELECT/INSERT)
    # 1ª ingestão: texto longo → produz 3 chunks
    # 2ª ingestão: texto curto → produz 1 chunk
    # Verificar que o DELETE foi emitido na 2ª chamada com filtro
    # cobrindo resource_id == 'abc' OR resource_id LIKE 'abc__chunk_%'
```

A implementação exata do teste fica a critério (mockar `db.execute` e capturar `call_args_list`, compilar com `literal_binds` e verificar SQL renderizado, similar ao padrão de `test_recall_memory_with_tags_filter` da Fase 4).

---

### Issue M1 — Services não devem chamar `commit()` diretamente

**Severidade:** Médio — bloqueia composição transacional em features futuras (ex: salvar 3 memórias atomicamente).

**Arquivos:**
- `app/services/embeddings.py` — função `ingest_item`, linha 178 (`await db.commit()`)
- `app/services/memory.py` — função `save_memory`, linha 59 (`await db.commit()`)
- `app/services/memory.py` — função `recall_memory`, linha 120 (`await db.commit()`)
- `app/database.py` — função `get_db`

**Por que está errado:** Services que chamam `commit()` impedem o handler/router de compor múltiplas operações em uma transação maior. Se um endpoint quiser fazer `save_memory(...)` duas vezes atomicamente e a segunda falhar, a primeira já foi commitada.

**Correção:**

**Passo 1** — Em `app/database.py`, ajustar `get_db()` para fazer commit/rollback automaticamente no exit do request:

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency que fornece uma sessão assíncrona do banco.

    Commit é feito automaticamente ao final do request se nenhuma
    exceção foi levantada. Rollback automático em caso de exceção.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Passo 2** — Em `app/services/memory.py::save_memory`, remover as linhas:
```python
await db.commit()
await db.refresh(memory)
```

E substituir por apenas:
```python
await db.flush()
await db.refresh(memory)
```

`flush()` envia o INSERT ao banco (necessário para `refresh` funcionar e popular `id`/`created_at`) sem commitar a transação.

**Passo 3** — Em `app/services/memory.py::recall_memory`, remover a linha:
```python
await db.commit()
```

(no bloco `if filtered:` após o `update`). O commit do request inteiro será feito pelo `get_db`.

**Passo 4** — Em `app/services/embeddings.py::ingest_item`, remover a linha:
```python
await db.commit()
```

**Passo 5** — Adicionar teste em `tests/test_edge_cases_memory.py`:

```python
@pytest.mark.asyncio
@patch("app.services.memory.generate_embedding", return_value=FAKE_VECTOR)
async def test_save_memory_does_not_commit(mock_emb):
    """save_memory faz flush mas não commit (transação fica aberta)."""
    db = _make_db()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    async def fake_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
    db.refresh = fake_refresh

    await save_memory(db, USER_ID, content="nota")

    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()
```

**Atenção a testes existentes:** Vários testes em `tests/test_edge_cases_memory.py` verificam `db.commit.assert_not_awaited()` ou `db.execute.await_count == 1`. Esses testes verificam o comportamento atual onde **só há commit em paths específicos**. Após a mudança, o serviço **nunca** comita, então:

- `test_save_memory_empty_content` — continua válido (já não comita).
- `test_recall_memory_below_threshold` — `db.commit.assert_not_awaited()` continua válido (não há filtered, sem update, sem commit). `db.execute.await_count == 1` continua válido.
- `test_recall_memory_updates_last_accessed` — `db.execute.await_count == 2` continua válido (SELECT + UPDATE). Adicionar `db.commit.assert_not_awaited()` para reforçar que o serviço não comita mais.

**Validação:** Suíte completa deve continuar passando, agora 122/122 ou 123/123 (com os novos testes de A2 e M1).

---

### Issue M2 — Migrations devem usar `server_default` para UUIDs

**Severidade:** Médio — `INSERT INTO ... (campos sem id)` via SQL puro (psql, dumps, scripts) falha.

**Arquivos:**
- `alembic/versions/001_initial_tables.py` — colunas `id` em `users` (linha 26), `graph_cache` (linha 41), `webhook_subscriptions` (linha 63)
- `alembic/versions/002_add_embeddings.py` — coluna `id` (linha 28)
- `alembic/versions/003_add_memories.py` — coluna `id` (linha 25)

**Estado atual (errado):**
```python
sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
```

**Por que está errado:** O parâmetro `default=` é Python-side — só é usado se o cliente Python NÃO passar o valor. No SQL DDL emitido, **não vira `DEFAULT gen_random_uuid()`**. Inserts via SQL puro (sem ORM) falham com `null value in column "id" violates not-null constraint`.

**Correção:** Trocar **em todas as 5 colunas `id` listadas acima** o `default=` por `server_default=`:

```python
sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
```

**O que NÃO mudar:** Os modelos SQLAlchemy (`app/models/user.py`, `cache.py`, `webhook.py`, `embedding.py`, `memory.py`) já usam `default=uuid.uuid4` Python-side. Mantém — funciona como dupla camada.

**Validação:** Suíte continua passando. Validação manual end-to-end (opcional): após `alembic upgrade head`, rodar `psql -c "\d+ memories"` e confirmar que a coluna `id` aparece como `DEFAULT gen_random_uuid()`.

---

## Resumo dos arquivos modificados

| Arquivo | Issues |
|---|---|
| `alembic/versions/001_initial_tables.py` | M2 |
| `alembic/versions/002_add_embeddings.py` | C1, M2 |
| `alembic/versions/003_add_memories.py` | C1, M2 |
| `app/database.py` | M1 |
| `app/services/embeddings.py` | A2, M1 |
| `app/services/memory.py` | M1 |
| `tests/test_property_recall_threshold.py` | A1 |
| `tests/test_edge_cases_embeddings.py` | A2 (novo teste) |
| `tests/test_edge_cases_memory.py` | M1 (novo teste + ajustes leves nos existentes) |

Total: 9 arquivos modificados, 0 novos.

---

## Critérios de aceitação (auditáveis)

A entrega só é aceita se TODOS os pontos abaixo passarem:

1. ✅ As migrations 002 e 003 importam `Vector` de `pgvector.sqlalchemy` e usam `Vector(384)` na coluna `vector`.
2. ✅ As 5 colunas `id` (3 em 001, 1 em 002, 1 em 003) usam `server_default=sa.text("gen_random_uuid()")`.
3. ✅ `app/database.py::get_db` faz commit no exit normal e rollback em exceção.
4. ✅ Nenhum dos 3 services (`ingest_item`, `save_memory`, `recall_memory`) chama `await db.commit()`.
5. ✅ `save_memory` chama `await db.flush()` antes de `await db.refresh(memory)`.
6. ✅ `ingest_graph_data` emite `DELETE FROM embeddings WHERE user_id=? AND service=? AND (resource_id=? OR resource_id LIKE '?__chunk_%')` antes de re-ingerir.
7. ✅ `tests/test_property_recall_threshold.py` usa `score >= 0.5` no assert.
8. ✅ Há um teste novo em `tests/test_edge_cases_embeddings.py` validando limpeza de órfãos.
9. ✅ Há um teste novo em `tests/test_edge_cases_memory.py` validando que `save_memory` não comita.
10. ✅ A suíte completa (`pytest -q`) passa, com pelo menos 123 testes verdes (121 atuais + 2 novos mínimos).
11. ✅ O property test `recall_threshold` passa para seeds de 0 a 20 (`pytest tests/test_property_recall_threshold.py --hypothesis-seed=N`, N de 0 a 20).

---

## Instrução global de documentação

Após implementar cada issue, gerar bloco de explicação no formato:

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

## Observação para o KIRO

Não otimizar, não adicionar features, não reorganizar imports gerais. **Apenas as 5 correções acima.** Se algo no caminho parece desconfortável ("ah, já que estou aqui, podia também..."), não faça — anote num comentário no PR description e o Claude Code triará.
