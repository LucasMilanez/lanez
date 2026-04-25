# Auditoria — Lanez Fase 1

Revisão do requirements.md, design.md e tasks.md gerados. Corrija os itens abaixo antes de implementar.

---

## CRÍTICOS

### 1. Background task de renovação de webhooks

**Arquivo:** `app/main.py` (Task 10.3)

FastAPI `BackgroundTasks` são request-scoped — só executam após uma requisição HTTP, não são timers. Com a implementação atual, as subscrições de webhook irão expirar sem renovação.

**Correção:** usar `asyncio.create_task` com loop no `lifespan`:

```python
async def renewal_loop():
    while True:
        await webhook_service.renew_subscriptions()
        await asyncio.sleep(1800)  # 30 minutos

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(renewal_loop())
    yield
    task.cancel()
```

Atualizar Task 10.3 para refletir essa abordagem.

---

### 2. Autenticação dos endpoints de dados não definida

**Arquivos:** `app/routers/graph.py` (Task 9.1), design Seção 10

Os endpoints `/me/events`, `/me/messages`, `/me/onenote/pages`, `/me/drive/root/children` dependem de `user_id`, mas nenhum requisito, design ou task define como o cliente passa e o servidor valida esse `user_id` após o OAuth.

Sem isso, qualquer pessoa pode chamar `/me/events?user_id=qualquer-uuid` sem autenticação.

**Correção:** emitir JWT interno assinado com `SECRET_KEY` no callback OAuth e validar via FastAPI dependency:

```python
# No callback OAuth — retornar JWT além do TokenResponse
access_token = jwt.encode({"user_id": str(user.id), "exp": ...}, settings.SECRET_KEY)

# Dependency para proteger endpoints de dados
async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)) -> User:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return await db.get(User, payload["user_id"])
```

Adicionar ao `requirements.txt`: `python-jose[cryptography]`

Atualizar:
- `requirements.md`: adicionar Requisito 18 (autenticação JWT para endpoints de dados)
- `design.md`: adicionar seção de JWT + dependency `get_current_user`
- `tasks.md`: adicionar Task 13 (implementar JWT + dependency)

---

## IMPORTANTES

### 3. Dependências de teste faltando

**Arquivo:** `requirements.txt` (Task 1.1)

As Tasks 11 e 12 implementam property-based tests e testes de integração, mas o `requirements.txt` não inclui as bibliotecas necessárias.

**Adicionar:**
```
pytest==8.3.0
pytest-asyncio==0.24.0
hypothesis==6.112.0
respx==0.21.0
```

---

### 4. Alembic ausente

**Arquivo:** `app/database.py`

O uso de `Base.metadata.create_all` funciona para desenvolvimento, mas sem Alembic não há histórico de migrations. Quando a Fase 2 adicionar novas tabelas, será impossível migrar um banco existente sem recriar do zero.

**Adicionar ao `requirements.txt`:** `alembic==1.13.0`

**Adicionar task:** inicializar Alembic e criar migration inicial para as 3 tabelas (User, GraphCache, WebhookSubscription).

---

## MENORES

### 5. Wording ambíguo no Requisito 3.4

**Arquivo:** `requirements.md`, R3 critério 4

Texto atual: `"THE Servidor_Auth SHALL registrar nunca o valor dos tokens"`

Corrigir para: `"THE Servidor_Auth SHALL NEVER log token values in any log output or error message"`

---

### 6. CORS deve ser configurável

**Arquivo:** `app/main.py` (Task 10.2)

O middleware CORS não deve usar `allow_origins=["*"]` fixo no código. Deve ser configurável via variável de ambiente.

**Adicionar ao `.env.example`:** `CORS_ORIGINS=http://localhost:5173`

**Corrigir no design:** `CORSMiddleware` com `allow_origins=settings.CORS_ORIGINS.split(",")`

---

## Resumo de ações

| Arquivo | Ação |
|---|---|
| `requirements.md` | Adicionar R18 (JWT auth) + corrigir R3.4 |
| `design.md` | Adicionar seção JWT + dependency + asyncio loop lifespan + CORS configurável |
| `tasks.md` | Atualizar Task 10.3 + adicionar Task 13 (JWT) + adicionar deps de teste |
| `requirements.txt` | Adicionar pytest, pytest-asyncio, hypothesis, respx, python-jose, alembic |
| `.env.example` | Adicionar CORS_ORIGINS |
