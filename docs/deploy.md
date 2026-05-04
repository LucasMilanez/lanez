# Deploy — Lanez Demo Público

Guia para colocar o Lanez no ar pela primeira vez.
Backend no Fly.io, frontend na Vercel, Postgres no Neon, Redis no Upstash.

## 1. Pré-requisitos

Instale as CLIs e crie contas (todas têm free tier):

- **flyctl**: `curl -L https://fly.io/install.sh | sh` (ou `brew install flyctl`)
- **vercel**: `npm i -g vercel`
- Conta **Fly.io**: https://fly.io/app/sign-up
- Conta **Neon**: https://console.neon.tech/signup
- Conta **Upstash**: https://console.upstash.com/login
- Conta **Vercel**: https://vercel.com/signup
- **Azure portal**: app registration existente com redirect URI
  `http://localhost:8000/auth/callback` (dev). Você vai adicionar a URI de prod.

## 2. Criar Postgres no Neon

Acesse https://console.neon.tech e crie um novo projeto (região: São Paulo ou US East).
Anote a connection string no formato `postgresql+asyncpg://user:pass@host/dbname`.

Habilite a extensão `vector` no SQL Editor do Neon:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## 3. Criar Redis no Upstash

Acesse https://console.upstash.com e crie um novo database Redis (região: Global).
Anote a connection string no formato `redis://default:token@host:port`.

## 4. Criar app no Fly.io

Na raiz do repositório:

```bash
fly launch --no-deploy
```

Quando perguntado, **rejeite** a criação de Postgres e Redis internos — usamos Neon e Upstash.
Confirme que o `fly.toml` gerado bate com o que está no repositório.

## 5. Setar secrets no Fly.io

```bash
fly secrets set \
  MICROSOFT_CLIENT_ID="..." \
  MICROSOFT_CLIENT_SECRET="..." \
  MICROSOFT_TENANT_ID="..." \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  WEBHOOK_CLIENT_STATE="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  DATABASE_URL="postgresql+asyncpg://..." \
  REDIS_URL="redis://default:...@...:port" \
  ANTHROPIC_API_KEY="..." \
  GROQ_API_KEY="..."
```

**Importante:** gere valores NOVOS para `SECRET_KEY` e `WEBHOOK_CLIENT_STATE`.
Não reutilize os de desenvolvimento.

## 6. Deploy do backend

```bash
fly deploy
```

Aguarde o healthcheck ficar verde. Confirme:

```bash
curl https://lanez.fly.dev/healthz
# Esperado: {"ok":true}
```

## 7. Deploy do frontend

Da pasta `frontend/`:

```bash
cd frontend
vercel --prod
```

Anote a URL gerada (ex: `lanez.vercel.app` ou `lanez-xxxxx.vercel.app`).

Se a URL não for exatamente `lanez.vercel.app`, atualize `CORS_ORIGINS` em `fly.toml`
e faça `fly deploy` novamente.

## 8. Atualizar Azure portal

No Azure portal, na app registration do Lanez:

1. Vá em **Authentication** → **Redirect URIs**
2. Adicione `https://lanez.fly.dev/auth/callback`
3. **Mantenha** `http://localhost:8000/auth/callback` (para dev local)
4. Salve

## 9. Smoke test

Abra `https://lanez.vercel.app` em navegador anônimo:

1. Faça login OAuth com sua conta Microsoft 365
2. Verifique que o dashboard carrega
3. Acesse `/audit` e confirme que a página renderiza
4. Teste geração de briefing (se houver dados no calendário)

## 10. Bootstrap de webhooks

> **ATENÇÃO: `setup-webhook.sh` é DESTRUTIVO.**
> Ele deleta TODAS as webhook subscriptions do banco de produção.
> Use apenas na primeira ida ao ar ou quando precisar resetar completamente.
> Não é uma rotina — é um bootstrap one-shot.

```bash
bash scripts/setup-webhook.sh
```

O `renewal_loop` do app recria as subscriptions automaticamente em até 30 minutos
com a URL de produção (`WEBHOOK_NOTIFICATION_URL`).

Para forçar a recriação imediatamente:

```bash
flyctl restart -a lanez
```

## 11. Atualizações futuras

Após o setup inicial, atualizações são automáticas:

```bash
git push origin main
```

Fly.io e Vercel detectam o push e fazem deploy automaticamente.

Para mudanças que envolvam migrations de banco, o startup do app roda
`alembic upgrade head` automaticamente. Se o startup falhar por erro de migration,
use o script de diagnóstico:

```bash
bash scripts/migrate.sh
```
