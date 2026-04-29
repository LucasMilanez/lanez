# Lanez — Briefing Fase 6b para KIRO

## Contexto crítico para esta fase

A Fase 6a entregou o painel React read-only com auth dual cookie+Bearer (commit `5876f6e`, 164/164 backend + 6/6 frontend). A Fase 6b adiciona **voz** ao painel — captura via mic, transcrição via Groq Whisper, e leitura por TTS de briefings. **Não há novas migrations**, **não há nova tabela de telemetria** nesta fase.

Como na 6a, este briefing é deliberadamente prescritivo. Frontend tem alto risco de divergência — o auditor (Claude Code) vai verificar fidelidade aos componentes shadcn, estados loading/empty/error, paleta de cores, e estrutura de arquivos.

---

## O que é o Lanez

MCP Server pessoal que conecta AI assistants aos dados do Microsoft 365. Branch `main` em `5876f6e`, suíte completa 164/164 backend + 6/6 smoke tests frontend.

---

## O que as Fases 1–6a entregaram (já existe — não reescrever)

```
app/
├── main.py              ← lifespan, CORS, registra: auth, graph, webhooks, mcp,
│                          briefings, status
├── config.py            ← Settings (CORS_ORIGINS, ANTHROPIC_API_KEY,
│                          BRIEFING_HISTORY_WINDOW_DAYS, ...) — adicionar GROQ_API_KEY
├── database.py          ← AsyncSessionLocal, get_db, get_redis
├── dependencies.py      ← get_current_user (cookie HttpOnly OU Bearer)
├── models/
│   ├── user.py
│   ├── cache.py
│   ├── webhook.py       ← WebhookSubscription (resource: String 255)
│   ├── embedding.py     ← Embedding (service: String 20, Vector 384, HNSW)
│   ├── memory.py        ← Memory (Vector 384, HNSW, GIN tags) — confirmar campos no pré-flight
│   └── briefing.py      ← Briefing (event_id, content, tokens, generated_at)
├── routers/
│   ├── auth.py          ← /auth/microsoft, /auth/callback (dual), /auth/me,
│   │                      /auth/logout, /auth/refresh
│   ├── graph.py
│   ├── webhooks.py
│   ├── mcp.py           ← 9 ferramentas (incluindo save_memory, recall_memory)
│   ├── briefings.py     ← GET /briefings (paginado), GET /briefings/{event_id}
│   └── status.py        ← GET /status
├── schemas/
│   ├── auth.py          ← UserMeResponse, TokenResponse
│   ├── briefing.py      ← BriefingResponse, BriefingListItem, BriefingListResponse
│   └── status.py        ← StatusResponse, StatusConfig, ServiceCount, etc.
└── services/
    ├── anthropic_client.py
    ├── briefing.py / briefing_context.py
    ├── embeddings.py
    ├── graph.py
    ├── memory.py        ← save_memory já existe (usado por MCP tool)
    ├── webhook.py
    ├── cache.py
    └── searxng.py

frontend/
├── src/
│   ├── App.tsx          ← ThemeProvider > QueryClientProvider > BrowserRouter
│   │                      > AuthProvider > Routes
│   ├── auth/            ← AuthContext, ProtectedRoute
│   ├── theme/           ← ThemeContext (com resolvedTheme), ThemeToggle
│   ├── lib/             ← api.ts (fetch + credentials: 'include'),
│   │                      queryClient.ts, utils.ts
│   ├── hooks/           ← useStatus, useBriefings, useBriefing
│   ├── components/      ← AppShell (Sidebar 240px + TopBar), StatusCard,
│   │                      TokenUsageChart, BriefingCard, BriefingMarkdown,
│   │                      EmptyState, ErrorState, LoadingSkeleton + ui/
│   └── pages/           ← LoginPage, DashboardPage, BriefingsListPage,
│                          BriefingDetailPage, SettingsPage
```

**Reutilizar das fases anteriores:**
- `get_current_user` em `app/dependencies.py` (auth dual)
- `MemoryService.save_memory` em `app/services/memory.py` — vai ser chamado pelo novo `POST /memories`
- `AppShell` e `TopBar` em `frontend/src/components/` — vão receber o botão de mic
- `BriefingDetailPage` em `frontend/src/pages/` — vai receber o botão de TTS
- `api` client em `frontend/src/lib/api.ts` — vai ser estendido para `postMultipart`

---

## Fase 6b — Voz (STT via Groq + TTS via SpeechSynthesis)

### Objetivo

Adicionar dois recursos de voz ao painel já entregue na 6a:

1. **Captura de voz por mic** (botão na TopBar) — usuário grava até 30 segundos, audio é enviado para `POST /voice/transcribe`, backend repassa para Groq Whisper, retorna texto. O texto é exibido num modal com duas ações:
   - **"Salvar como memória"** → `POST /memories` (endpoint REST novo, reaproveitando `MemoryService` existente)
   - **"Buscar nos briefings"** → navega para `/briefings?q=<texto>`

2. **TTS de briefings** (botão no `BriefingDetailPage`) — usa `SpeechSynthesis` nativo do browser para ler o conteúdo Markdown (com markdown removido), com voz pt-BR quando disponível, controles play/pause.

### O que NÃO entra na 6b

- **Sem nova migration / nova tabela** — telemetria de voz fica em logger por enquanto (custo Groq Whisper ~$0.04/h, irrelevante para 5 áudios de 30s/dia)
- **Sem TTS fora de briefings** (toasts, mensagens, etc.) — somente `BriefingDetailPage`
- **Sem voz nas páginas Login/Dashboard/Settings** — apenas TopBar (todas as rotas autenticadas) + BriefingDetailPage
- **Sem suporte a >30s de áudio** — limite hard tanto no client quanto no server
- **Sem upload de arquivo de áudio** (drag & drop, file picker) — apenas mic
- **Sem visualização de waveform** — somente um indicador "● Gravando" + timer (00:15 / 00:30)
- **Sem armazenamento de transcrições** — efêmeras (modal fecha → texto se perde a menos que usuário tenha clicado em "Salvar como memória")
- **Sem persistência de histórico de comandos por voz** — fora do escopo
- **Página `/audit`** continua na **Fase 7** (junto com audit log no backend)

### Decisões técnicas (já aprovadas pelo usuário)

| Decisão | Escolha | Justificativa |
|---|---|---|
| Provider STT | Groq Whisper (`whisper-large-v3-turbo`) | Custo ~$0.04/h, latência baixa, qualidade adequada |
| Provider TTS | `SpeechSynthesis` nativo do browser | Zero custo, zero dependência, suficiente para leitura de briefings |
| Captura de áudio | `MediaRecorder` API nativa (sem libs como RecordRTC) | Padrão Web, sem bloat |
| Formato de áudio | `audio/webm` (default Chrome/Edge/Firefox) ou `audio/mp4` (Safari) — passa pelo Groq como está | Groq aceita ambos |
| Duração máxima | **30 segundos** (auto-stop client + validação por tamanho server) | Cobre 99% dos comandos curtos; evita uploads grandes |
| Tamanho máximo no server | **5 MB** | Margem para 30s a 128 kbps |
| Persistência de transcrição | **Não persistir** — retorna ao client e some | Privacidade + simplicidade; salvar só explícito via "Salvar como memória" |
| Telemetria | Apenas log estruturado (`logger.info`) com `user_id`, `duration_seconds`, sem áudio | Custo é desprezível, não justifica tabela |
| Modal de voz | shadcn `Dialog` (NÃO Popover, NÃO Drawer) | Consistente com padrão da Fase 6a |
| Endpoint memória | `POST /memories` REST novo, body JSON `{content: str, tags: list[str]}` | Painel não fala MCP JSON-RPC diretamente; REST é mais simples |
| Fluxo de TTS | `SpeechSynthesisUtterance` com `lang="pt-BR"` se disponível | Tenta português; cai pra default se navegador não tiver |
| Erro de permissão | Modal mostra explicação clara + link para configurações de site do navegador | Mic precisa permissão explícita |
| Browser test | Manual (Chrome + Firefox em dev) — Vitest mocka `MediaRecorder` e `SpeechSynthesis` | jsdom não suporta nenhum dos dois |

---

## Pré-flight obrigatório

Antes de gerar a spec, executar:

```bash
# 1) Confirmar campos do modelo Memory — atenção especial ao nome real do
#    campo de tags (pode ser `tags` com ARRAY(String), ou outro nome)
grep -n "Column\|Mapped\[" app/models/memory.py
grep -n "tags\|ARRAY" app/models/memory.py

# 2) Inspecionar interface atual de save_memory no service
grep -n "async def save_memory\|def save_memory" app/services/memory.py

# 3) Confirmar construtor de MemoryService — precisamos saber se aceita
#    args (embeddings_client, http_client, etc.) ou se é simples MemoryService()
grep -n "class MemoryService\|def __init__" app/services/memory.py | head -5

# 4) Confirmar que POST /memories NÃO existe (evitar conflito)
grep -rn "@router.post" app/routers/ | grep -i memor

# 5) Confirmar que GROQ_API_KEY ainda não está em Settings (vai ser adicionada)
grep -n "GROQ_API_KEY" app/config.py

# 6) Confirmar shape de retorno do save_memory (id, created_at, etc.)
grep -n "return\|Memory(" app/services/memory.py | head -20
```

Reportar no bloco "Explicação — Tarefa 1" os achados:
- Lista de campos reais de `Memory` (esperado: id, user_id, content, tags, vector, created_at) — **confirmar o nome real do campo de tags**
- Assinatura de `MemoryService.save_memory(...)`
- **Construtor de `MemoryService`** — se exigir argumentos, ajustar `app/routers/memories.py` para construir corretamente (não modificar o service)
- Confirmação de que não há `POST /memories` ainda
- Confirmação de que `GROQ_API_KEY` ainda não está em `Settings`
- Tipo de retorno do `save_memory` (objeto Memory ou tuple ou dict?)

Se algum destes pontos divergir das suposições do briefing, **ajustar o código gerado para o que realmente existe**, não inventar. Documentar as divergências.

---

## Parte B — Mudanças no Backend

São **3 mudanças** no backend. Implementar nesta ordem, com testes em cada uma:

### 6b.B.1 — Cliente Groq Whisper (`app/services/groq_voice.py` NOVO)

Cliente fino que envia áudio ao Groq e devolve transcrição. Sem retries complexos, sem cache — apenas wrapper.

**Nova variável em `app/config.py`:**

```python
GROQ_API_KEY: str = ""
GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
VOICE_MAX_AUDIO_BYTES: int = 5 * 1024 * 1024  # 5 MB
VOICE_MAX_DURATION_SECONDS: int = 30
```

**Implementação exata (`app/services/groq_voice.py`):**

```python
"""Cliente Groq Whisper para transcrição de áudio — Fase 6b.

Envia áudio multipart para a API da Groq e retorna a transcrição.
Não persiste o áudio. Não armazena a transcrição.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_HTTP_TIMEOUT = 60.0


class GroqTranscriptionError(Exception):
    """Falha ao transcrever via Groq (rede, autenticação, payload)."""


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Transcreve áudio via Groq Whisper.

    Retorna o texto cru. Levanta GroqTranscriptionError em caso de falha.
    """
    if not settings.GROQ_API_KEY:
        raise GroqTranscriptionError("GROQ_API_KEY não configurado")

    files = {"file": (filename, audio_bytes, content_type)}
    data = {
        "model": settings.GROQ_WHISPER_MODEL,
        "language": "pt",
        "response_format": "json",
    }
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(
                GROQ_TRANSCRIPTION_URL,
                files=files,
                data=data,
                headers=headers,
            )
        except httpx.HTTPError as e:
            logger.exception("Falha de rede ao chamar Groq Whisper")
            raise GroqTranscriptionError(f"Erro de rede: {e}") from e

    if resp.status_code != 200:
        logger.error(
            "Groq Whisper retornou %d — body=%s",
            resp.status_code,
            resp.text[:500],
        )
        raise GroqTranscriptionError(
            f"Groq retornou {resp.status_code}"
        )

    payload = resp.json()
    text = (payload.get("text") or "").strip()
    if not text:
        raise GroqTranscriptionError("Groq retornou texto vazio")

    return text
```

**Decisões importantes:**
- `language="pt"` força detecção de português — Lanez é single-user pt-BR
- `response_format="json"` retorna `{"text": "..."}` — formato mais simples
- Sem retries (custo de retry pode duplicar preço; deixa o user re-gravar)
- Logger NÃO loga conteúdo do áudio nem da transcrição — privacidade

### 6b.B.2 — `POST /voice/transcribe` (`app/routers/voice.py` NOVO)

Endpoint que recebe `multipart/form-data` com campo `audio`, valida tamanho, chama `groq_voice.transcribe_audio`, retorna JSON.

**Implementação exata (`app/routers/voice.py`):**

```python
"""Router de voz — captura via mic e transcrição via Groq Whisper. Fase 6b."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_current_user
from app.models.user import User
from app.services.groq_voice import GroqTranscriptionError, transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceTranscriptionResponse(BaseModel):
    transcription: str
    duration_ms: int  # tempo total da chamada (recebimento + Groq)


_ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
}


@router.post("/transcribe", response_model=VoiceTranscriptionResponse)
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> VoiceTranscriptionResponse:
    """Recebe áudio do mic e retorna transcrição via Groq Whisper.

    Limites:
    - Tamanho máximo: settings.VOICE_MAX_AUDIO_BYTES (5 MB)
    - Content-Type: audio/webm, audio/ogg, audio/mp4, audio/mpeg, audio/wav, audio/flac
    """
    # Chrome envia "audio/webm;codecs=opus" — separar parâmetros antes de validar
    raw_ct = (audio.content_type or "").split(";")[0].strip()
    if raw_ct not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content-Type não suportado: {audio.content_type}",
        )

    audio_bytes = await audio.read()
    if len(audio_bytes) > settings.VOICE_MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Áudio excede {settings.VOICE_MAX_AUDIO_BYTES} bytes "
                f"(recebido: {len(audio_bytes)})"
            ),
        )

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Áudio vazio",
        )

    started_at = time.monotonic()
    try:
        text = await transcribe_audio(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            content_type=raw_ct,
        )
    except GroqTranscriptionError as e:
        logger.warning(
            "Falha na transcrição para user_id=%s: %s",
            user.id,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao transcrever áudio",
        )

    elapsed_ms = int((time.monotonic() - started_at) * 1000)

    # Telemetria mínima — sem persistir áudio nem transcrição
    logger.info(
        "voice.transcribe user_id=%s bytes=%d duration_ms=%d",
        user.id,
        len(audio_bytes),
        elapsed_ms,
    )

    return VoiceTranscriptionResponse(
        transcription=text,
        duration_ms=elapsed_ms,
    )
```

**Registrar em `app/main.py`** junto aos demais routers: `app.include_router(voice.router)`.

**Decisões importantes:**
- `UploadFile = File(...)` recebe streaming, mas chamamos `audio.read()` para validar tamanho — aceitável para 5 MB
- Validação de Content-Type é defensiva contra clients que mandam `application/octet-stream`
- `502 Bad Gateway` é a resposta correta para falha de upstream (Groq)
- Telemetria via `logger.info` — sem áudio, sem transcrição (privacidade)

### 6b.B.3 — `POST /memories` (REST — `app/routers/memories.py` NOVO)

Endpoint REST para o painel salvar memórias diretamente, sem precisar passar pelo MCP JSON-RPC. Reaproveita `MemoryService.save_memory` (confirmado no pré-flight).

**Schema novo (`app/schemas/memory.py` NOVO):**

```python
"""Schemas Pydantic para memórias REST — Fase 6b."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("content")
    @classmethod
    def _strip_and_reject_whitespace(cls, v: str) -> str:
        """min_length=1 sozinho aceita "   " (3 espaços). Rejeitar."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("content não pode ser apenas whitespace")
        return stripped


class MemoryResponse(BaseModel):
    id: UUID
    content: str
    tags: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
```

**Endpoint (`app/routers/memories.py` NOVO):**

```python
"""Router REST para criação de memórias via painel — Fase 6b.

Reaproveita app.services.memory.MemoryService.save_memory.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.memory import MemoryCreateRequest, MemoryResponse
from app.services.memory import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """Cria nova memória. Gera embedding internamente via MemoryService."""
    service = MemoryService()
    memory = await service.save_memory(
        user_id=user.id,
        content=body.content,
        tags=body.tags,
        db=db,
    )
    return memory
```

**Atenção do pré-flight:** se a assinatura real de `MemoryService.save_memory` divergir (ex.: nomes de parâmetros diferentes, retorno é dict em vez de Memory), **ajustar a chamada no router para a assinatura real**, não modificar o service.

**Registrar em `app/main.py`**: `app.include_router(memories.router)`.

### 6b.B.4 — Testes do backend (14 novos obrigatórios)

**Para `/voice/transcribe`:**
- `test_voice_transcribe_returns_text` — mock `transcribe_audio`, verifica 200 + `transcription` no body
- `test_voice_transcribe_rejects_unsupported_content_type` — content-type `application/json` → 415
- `test_voice_transcribe_rejects_oversized_audio` — body > 5 MB → 413
- `test_voice_transcribe_rejects_empty_audio` — body vazio → 400
- `test_voice_transcribe_returns_502_on_groq_failure` — mock `transcribe_audio` levantando `GroqTranscriptionError` → 502
- `test_voice_transcribe_requires_auth` — sem cookie/Bearer → 401

**Para `groq_voice.transcribe_audio`:**
- `test_groq_voice_raises_on_missing_api_key` — settings mockado com key vazia → `GroqTranscriptionError`
- `test_groq_voice_raises_on_non_200_status` — httpx mock retornando 500 → `GroqTranscriptionError`
- `test_groq_voice_raises_on_empty_text` — Groq retorna `{"text": ""}` → `GroqTranscriptionError`

**Para `POST /memories`:**
- `test_create_memory_201_with_id_and_created_at` — mock `MemoryService.save_memory` retornando objeto Memory
- `test_create_memory_validates_min_length` — body com `content=""` → 422
- `test_create_memory_rejects_whitespace_only_content` — body com `content="   "` → 422 (validator de strip)
- `test_create_memory_validates_max_tags` — body com 21 tags → 422
- `test_create_memory_requires_auth` — sem cookie/Bearer → 401

Os testes devem usar `app.dependency_overrides` para `get_current_user` e `get_db`, conforme padrão da Fase 6a.

---

## Parte F — Frontend

São **5 mudanças** no frontend, organizadas em 3 grupos:

### 6b.F.1 — Estrutura de diretórios (incremental)

```
frontend/src/
├── components/
│   ├── (existentes ...)
│   └── voice/                       ← NOVO diretório
│       ├── MicButton.tsx            ← NOVO — botão da TopBar
│       ├── VoiceCaptureDialog.tsx   ← NOVO — modal Dialog do shadcn
│       ├── RecordingIndicator.tsx   ← NOVO — pulse + timer
│       └── TranscriptionResult.tsx  ← NOVO — texto + 2 botões de ação
├── components/
│   └── BriefingTTSButton.tsx        ← NOVO (não dentro de voice/) — específico de briefing
├── hooks/
│   ├── (existentes ...)
│   ├── useVoiceRecorder.ts          ← NOVO — encapsula MediaRecorder
│   ├── useTranscribe.ts             ← NOVO — TanStack mutation para POST /voice/transcribe
│   ├── useCreateMemory.ts           ← NOVO — TanStack mutation para POST /memories
│   └── useSpeechSynthesis.ts        ← NOVO — encapsula SpeechSynthesis
├── lib/
│   ├── api.ts                        ← MOD — adicionar `api.postMultipart`
│   └── stripMarkdown.ts              ← NOVO — utilitário para TTS
└── __tests__/
    ├── (existentes ...)
    ├── MicButton.test.tsx            ← NOVO
    ├── VoiceCaptureDialog.test.tsx   ← NOVO
    └── BriefingTTSButton.test.tsx    ← NOVO
```

**Não criar:** `frontend/src/voice/` (use `components/voice/`), `frontend/src/services/`, `frontend/src/utils/` (use `lib/`).

**Modificar `frontend/vite.config.ts`** — o proxy atual cobre `/auth /briefings /status /mcp` (Fase 6a). Acrescentar **`/voice` e `/memories`** apontando para `http://localhost:8000`:

```ts
proxy: {
  "/auth": "http://localhost:8000",
  "/briefings": "http://localhost:8000",
  "/status": "http://localhost:8000",
  "/mcp": "http://localhost:8000",
  "/voice": "http://localhost:8000",      // Fase 6b
  "/memories": "http://localhost:8000",   // Fase 6b
}
```

Sem essas duas linhas, requests do frontend em dev caem no handler de estático do Vite e retornam 404 — falha silenciosa que confunde quem testa.

### 6b.F.2 — Cliente API estendido (`frontend/src/lib/api.ts`)

Adicionar método `postMultipart` ao cliente existente. Não substituir nada.

```ts
// Adicionar à api existente:
async function requestMultipart<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    body: formData,  // NÃO setar Content-Type — fetch + FormData fazem com boundary correto
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* mantém statusText */
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  postMultipart: <T>(path: string, formData: FormData) =>
    requestMultipart<T>(path, formData),
};
```

**Atenção:** **NÃO** setar `Content-Type` manualmente em `requestMultipart`. O browser gera o boundary correto se você omitir o header.

### 6b.F.3 — Hooks de voz

#### `useVoiceRecorder.ts`

Encapsula `MediaRecorder` + permissões + auto-stop em 30s.

```ts
import { useCallback, useEffect, useRef, useState } from "react";

type State = "idle" | "requesting-permission" | "recording" | "stopping" | "error";

interface UseVoiceRecorderResult {
  state: State;
  errorMessage: string | null;
  elapsedSeconds: number;
  start: () => Promise<void>;
  stop: () => Promise<Blob | null>;
  reset: () => void;
}

const MAX_DURATION_SECONDS = 30;

export function useVoiceRecorder(): UseVoiceRecorderResult {
  const [state, setState] = useState<State>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null);

  const cleanupTimer = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setState("requesting-permission");
    setErrorMessage(null);
    setElapsedSeconds(0);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = () => {
        cleanupTimer();
        cleanupStream();
        const mime = recorder.mimeType || "audio/webm";
        const blob = chunksRef.current.length > 0
          ? new Blob(chunksRef.current, { type: mime })
          : null;
        setState("idle");
        stopResolverRef.current?.(blob);
        stopResolverRef.current = null;
      };

      recorder.start();
      setState("recording");

      // Tick puro — apenas atualiza o contador. Auto-stop fica num useEffect separado.
      tickRef.current = window.setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } catch (err) {
      cleanupStream();
      setState("error");
      setErrorMessage(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Permissão de microfone negada. Habilite nas configurações do navegador."
          : "Não foi possível acessar o microfone."
      );
    }
  }, [cleanupTimer, cleanupStream]);

  const stop = useCallback(() => {
    return new Promise<Blob | null>((resolve) => {
      if (recorderRef.current?.state === "recording") {
        stopResolverRef.current = resolve;
        setState("stopping");
        recorderRef.current.stop();
      } else {
        resolve(null);
      }
    });
  }, []);

  const reset = useCallback(() => {
    // Se ainda gravando (usuário fechou o dialog em meio à gravação),
    // parar o MediaRecorder antes de soltar tracks/timer.
    if (recorderRef.current?.state === "recording") {
      try {
        recorderRef.current.stop();
      } catch {
        /* ignorar — recorder já em estado inválido */
      }
    }
    cleanupTimer();
    cleanupStream();
    recorderRef.current = null;
    chunksRef.current = [];
    stopResolverRef.current = null;
    setElapsedSeconds(0);
    setState("idle");
    setErrorMessage(null);
  }, [cleanupTimer, cleanupStream]);

  // Auto-stop em MAX_DURATION_SECONDS — separado do tick para evitar
  // side effects dentro do state updater (problemático em Strict Mode).
  useEffect(() => {
    if (
      elapsedSeconds >= MAX_DURATION_SECONDS &&
      recorderRef.current?.state === "recording"
    ) {
      recorderRef.current.stop();
    }
  }, [elapsedSeconds]);

  useEffect(() => () => {
    cleanupTimer();
    cleanupStream();
  }, [cleanupTimer, cleanupStream]);

  return { state, errorMessage, elapsedSeconds, start, stop, reset };
}
```

**Decisões críticas:**
- `MediaRecorder` sem `mimeType` explícito — browser escolhe (Chrome: webm/opus; Safari: mp4)
- Auto-stop em `MAX_DURATION_SECONDS = 30` — definido em const local, não como prop (consistente com server)
- Cleanup de tracks no `onstop` para liberar o LED do mic
- `stop()` retorna Promise resolvida no callback `onstop` — evita race entre stop e dataavailable
- Tratamento explícito de `NotAllowedError` (denied) com mensagem em pt-BR

#### `useTranscribe.ts`

```ts
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

interface VoiceTranscriptionResponse {
  transcription: string;
  duration_ms: number;
}

export function useTranscribe() {
  return useMutation<VoiceTranscriptionResponse, ApiError, Blob>({
    mutationFn: async (audioBlob: Blob) => {
      const form = new FormData();
      const filename = audioBlob.type.includes("mp4") ? "audio.mp4" : "audio.webm";
      form.append("audio", audioBlob, filename);
      return api.postMultipart<VoiceTranscriptionResponse>("/voice/transcribe", form);
    },
  });
}
```

#### `useCreateMemory.ts`

```ts
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

interface MemoryResponse {
  id: string;
  content: string;
  tags: string[];
  created_at: string;
}

interface CreateMemoryInput {
  content: string;
  tags?: string[];
}

export function useCreateMemory() {
  return useMutation<MemoryResponse, ApiError, CreateMemoryInput>({
    mutationFn: ({ content, tags = [] }) =>
      api.post<MemoryResponse>("/memories", { content, tags }),
  });
}
```

#### `useSpeechSynthesis.ts`

```ts
import { useCallback, useEffect, useState } from "react";

type State = "idle" | "speaking" | "paused";

interface UseSpeechSynthesisResult {
  state: State;
  speak: (text: string) => void;
  pause: () => void;
  resume: () => void;
  cancel: () => void;
  supported: boolean;
}

export function useSpeechSynthesis(): UseSpeechSynthesisResult {
  const supported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const [state, setState] = useState<State>("idle");

  // Chrome popula getVoices() assincronamente — disparar carregamento no mount
  // e ouvir 'voiceschanged' garante que a voz pt-BR fique disponível na 1ª chamada.
  useEffect(() => {
    if (!supported) return;
    window.speechSynthesis.getVoices(); // trigger inicial
    const handler = () => {
      window.speechSynthesis.getVoices(); // mantém o cache do browser quente
    };
    window.speechSynthesis.addEventListener("voiceschanged", handler);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", handler);
    };
  }, [supported]);

  useEffect(() => {
    return () => {
      if (supported) window.speechSynthesis.cancel();
    };
  }, [supported]);

  const speak = useCallback((text: string) => {
    if (!supported || !text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "pt-BR";

    const voices = window.speechSynthesis.getVoices();
    const ptVoice = voices.find((v) => v.lang.startsWith("pt"));
    if (ptVoice) utter.voice = ptVoice;

    utter.onstart = () => setState("speaking");
    utter.onend = () => setState("idle");
    utter.onerror = () => setState("idle");

    window.speechSynthesis.speak(utter);
  }, [supported]);

  const pause = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.pause();
    setState("paused");
  }, [supported]);

  const resume = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.resume();
    setState("speaking");
  }, [supported]);

  const cancel = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setState("idle");
  }, [supported]);

  return { state, speak, pause, resume, cancel, supported };
}
```

### 6b.F.4 — Componentes de voz

#### `MicButton.tsx` (na TopBar)

```tsx
import { Mic } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { VoiceCaptureDialog } from "@/components/voice/VoiceCaptureDialog";

export function MicButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Capturar voz"
        onClick={() => setOpen(true)}
      >
        <Mic className="h-4 w-4" />
      </Button>
      <VoiceCaptureDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
```

**Modificar `frontend/src/components/TopBar.tsx`** para incluir `<MicButton />` à esquerda do `<ThemeToggle />`. **Não tocar em mais nada da TopBar.**

#### `RecordingIndicator.tsx`

```tsx
import { cn } from "@/lib/utils";

interface RecordingIndicatorProps {
  elapsedSeconds: number;
  maxSeconds?: number;
}

export function RecordingIndicator({
  elapsedSeconds,
  maxSeconds = 30,
}: RecordingIndicatorProps) {
  // Formato MM:SS sempre com 2 dígitos em cada — "00:05 / 00:30"
  const formatted = `${String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:${String(
    elapsedSeconds % 60
  ).padStart(2, "0")}`;
  const max = `${String(Math.floor(maxSeconds / 60)).padStart(2, "0")}:${String(
    maxSeconds % 60
  ).padStart(2, "0")}`;

  return (
    <div className="flex items-center gap-3">
      <span className={cn("h-3 w-3 rounded-full bg-red-500 animate-pulse")} />
      <span className="font-mono text-sm">
        {formatted} / {max}
      </span>
    </div>
  );
}
```

#### `TranscriptionResult.tsx`

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";  // adicionar via shadcn
import { useCreateMemory } from "@/hooks/useCreateMemory";

interface TranscriptionResultProps {
  initialText: string;
  onClose: () => void;
}

export function TranscriptionResult({ initialText, onClose }: TranscriptionResultProps) {
  const navigate = useNavigate();
  const createMemory = useCreateMemory();
  const [text, setText] = useState(initialText);

  const handleSaveAsMemory = () => {
    createMemory.mutate(
      { content: text, tags: ["voz"] },
      {
        onSuccess: () => {
          toast.success("Memória salva");
          onClose();
        },
        onError: (err) => {
          toast.error(`Falha ao salvar: ${err.detail}`);
        },
      }
    );
  };

  const handleSearchInBriefings = () => {
    const q = encodeURIComponent(text.trim());
    navigate(`/briefings?q=${q}`);
    onClose();
  };

  return (
    <div className="space-y-4">
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        className="font-mono text-sm"
        aria-label="Transcrição editável"
      />
      <div className="flex gap-2 justify-end">
        <Button
          variant="secondary"
          onClick={handleSearchInBriefings}
          disabled={!text.trim()}
        >
          Buscar nos briefings
        </Button>
        <Button
          onClick={handleSaveAsMemory}
          disabled={!text.trim() || createMemory.isPending}
        >
          {createMemory.isPending ? "Salvando..." : "Salvar como memória"}
        </Button>
      </div>
    </div>
  );
}
```

**Importante:** `Textarea` do shadcn/ui ainda não foi adicionado na 6a. **Adicionar via** `npx shadcn@latest add textarea` na Tarefa 1 do frontend (6b.F).

#### `VoiceCaptureDialog.tsx`

```tsx
import { useState } from "react";
import { toast } from "sonner";
import { Mic, Square } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";  // adicionar via shadcn add dialog
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { RecordingIndicator } from "@/components/voice/RecordingIndicator";
import { TranscriptionResult } from "@/components/voice/TranscriptionResult";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { useTranscribe } from "@/hooks/useTranscribe";

interface VoiceCaptureDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function VoiceCaptureDialog({ open, onOpenChange }: VoiceCaptureDialogProps) {
  const recorder = useVoiceRecorder();
  const transcribe = useTranscribe();
  const [transcription, setTranscription] = useState<string | null>(null);

  const handleClose = () => {
    recorder.reset();
    transcribe.reset();
    setTranscription(null);
    onOpenChange(false);
  };

  const handleStart = async () => {
    setTranscription(null);
    transcribe.reset();
    await recorder.start();
  };

  const handleStop = async () => {
    const blob = await recorder.stop();
    if (!blob) {
      toast.error("Nenhum áudio capturado");
      return;
    }
    transcribe.mutate(blob, {
      onSuccess: (data) => setTranscription(data.transcription),
      onError: (err) => toast.error(`Falha na transcrição: ${err.detail}`),
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(o) : handleClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Captura por voz</DialogTitle>
          <DialogDescription>
            Grave até 30 segundos. A gravação para automaticamente no limite.
          </DialogDescription>
        </DialogHeader>

        {recorder.state === "error" && recorder.errorMessage && (
          <Alert variant="destructive">
            <AlertDescription>{recorder.errorMessage}</AlertDescription>
          </Alert>
        )}

        {transcription === null ? (
          <div className="flex flex-col items-center gap-4 py-6">
            {recorder.state === "recording" || recorder.state === "stopping" ? (
              <>
                <RecordingIndicator elapsedSeconds={recorder.elapsedSeconds} />
                <Button
                  variant="destructive"
                  size="lg"
                  onClick={handleStop}
                  disabled={recorder.state === "stopping"}
                >
                  <Square className="h-4 w-4 mr-2" />
                  Parar
                </Button>
              </>
            ) : transcribe.isPending ? (
              <p className="text-sm text-muted-foreground">Transcrevendo...</p>
            ) : (
              <Button size="lg" onClick={handleStart}>
                <Mic className="h-4 w-4 mr-2" />
                Iniciar gravação
              </Button>
            )}
          </div>
        ) : (
          <TranscriptionResult initialText={transcription} onClose={handleClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}
```

**Componentes shadcn adicionais a instalar nesta fase:**

```bash
npx shadcn@latest add dialog textarea
```

#### `BriefingTTSButton.tsx`

Botão na `BriefingDetailPage` que lê o conteúdo do briefing.

```tsx
import { Pause, Play, StopCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSpeechSynthesis } from "@/hooks/useSpeechSynthesis";
import { stripMarkdown } from "@/lib/stripMarkdown";

interface BriefingTTSButtonProps {
  content: string;
}

export function BriefingTTSButton({ content }: BriefingTTSButtonProps) {
  const tts = useSpeechSynthesis();

  if (!tts.supported) return null;

  if (tts.state === "speaking") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={tts.pause}>
          <Pause className="h-4 w-4 mr-2" />
          Pausar
        </Button>
        <Button variant="outline" size="sm" onClick={tts.cancel}>
          <StopCircle className="h-4 w-4 mr-2" />
          Parar
        </Button>
      </div>
    );
  }

  if (tts.state === "paused") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={tts.resume}>
          <Play className="h-4 w-4 mr-2" />
          Continuar
        </Button>
        <Button variant="outline" size="sm" onClick={tts.cancel}>
          <StopCircle className="h-4 w-4 mr-2" />
          Parar
        </Button>
      </div>
    );
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => tts.speak(stripMarkdown(content))}
    >
      <Play className="h-4 w-4 mr-2" />
      Ouvir resumo
    </Button>
  );
}
```

**Modificar `frontend/src/pages/BriefingDetailPage.tsx`** para incluir `<BriefingTTSButton content={briefing.content} />` ao lado dos metadados (ou logo abaixo do título). **Não reescrever a página inteira** — adicionar apenas o botão.

#### `lib/stripMarkdown.ts`

```ts
/**
 * Remove sintaxe Markdown do texto para envio ao SpeechSynthesis.
 * Não é completo — cobre os elementos mais comuns gerados pelo Haiku.
 */
export function stripMarkdown(md: string): string {
  return md
    // Headers
    .replace(/^#{1,6}\s+/gm, "")
    // Bold/italic
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    // Inline code
    .replace(/`([^`]+)`/g, "$1")
    // Code fences
    .replace(/```[\s\S]*?```/g, "")
    // Links — mantém só o texto
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    // Bullets
    .replace(/^[-*+]\s+/gm, "")
    // Numbered lists
    .replace(/^\d+\.\s+/gm, "")
    // Blockquotes — Haiku às vezes gera "> texto"; sem isso o TTS lê "maior que"
    .replace(/^>\s+/gm, "")
    // Tabela: remove pipes e separadores
    .replace(/^\|.+\|$/gm, (line) => line.replace(/\|/g, " ").trim())
    .replace(/^[\s|:-]+$/gm, "")
    // Múltiplas quebras
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
```

### 6b.F.5 — Testes do frontend (mínimo 3 novos)

- `MicButton.test.tsx` — clicar abre dialog (`open === true` após click)
- `VoiceCaptureDialog.test.tsx` — render inicial mostra botão "Iniciar gravação"; mockando `useVoiceRecorder` em estado `error`, mostra Alert
- `BriefingTTSButton.test.tsx` — quando `useSpeechSynthesis` retorna `supported: false`, componente renderiza `null`; quando `state === "speaking"`, mostra botões "Pausar" e "Parar"

**Mocks necessários no `setup.ts`:**

```ts
// Adicionar ao setup existente:
import { vi } from "vitest";

// MediaRecorder e getUserMedia (jsdom não suporta)
Object.defineProperty(global.navigator, "mediaDevices", {
  writable: true,
  value: { getUserMedia: vi.fn() },
});

global.MediaRecorder = vi.fn().mockImplementation(() => ({
  start: vi.fn(),
  stop: vi.fn(),
  ondataavailable: null,
  onstop: null,
  state: "inactive",
  mimeType: "audio/webm",
})) as unknown as typeof MediaRecorder;

// SpeechSynthesis — incluir addEventListener/removeEventListener para o
// useEffect de pré-aquecimento de voices (B6) não estourar em jsdom.
Object.defineProperty(global.window, "speechSynthesis", {
  writable: true,
  value: {
    speak: vi.fn(),
    cancel: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    getVoices: vi.fn(() => []),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  },
});

global.SpeechSynthesisUtterance = vi.fn().mockImplementation((text) => ({
  text,
  lang: "",
  voice: null,
  onstart: null,
  onend: null,
  onerror: null,
})) as unknown as typeof SpeechSynthesisUtterance;
```

---

## Critérios de aceitação

A entrega 6b é aceita se TODOS abaixo passarem:

### Backend
1. `app/services/groq_voice.py` existe com `transcribe_audio` que retorna texto ou levanta `GroqTranscriptionError`
2. `POST /voice/transcribe` aceita `multipart/form-data` com campo `audio`, valida content-type e tamanho, retorna `VoiceTranscriptionResponse` (transcription + duration_ms)
3. `POST /voice/transcribe` retorna 415 para content-type não suportado, 413 para >5 MB, 400 para body vazio, 502 para falha Groq, 401 sem auth
4. `POST /memories` aceita JSON `{content, tags}`, retorna 201 com Memory criada via `MemoryService.save_memory`
5. `POST /memories` valida `content` min_length=1 max_length=10_000 e `tags` max_length=20 (422 caso contrário)
6. `app/main.py` registra os 2 routers novos: `voice.router` e `memories.router`
7. `app/config.py` ganha 4 settings: `GROQ_API_KEY`, `GROQ_WHISPER_MODEL`, `VOICE_MAX_AUDIO_BYTES`, `VOICE_MAX_DURATION_SECONDS`
8. **Suíte completa de testes passa sem flags `-k` ou `-x`** — meta exata `164 baseline + 14 novos = 178 verdes` (6 voice + 3 groq + 5 memories conforme §6b.B.4)

### Frontend
9. `frontend/` tem os arquivos novos da seção 6b.F.1 (com componentes shadcn `dialog` e `textarea` adicionados)
10. `MicButton` aparece na `TopBar` à esquerda do `ThemeToggle`, abre `VoiceCaptureDialog` ao clicar
11. `VoiceCaptureDialog` apresenta 4 estados visuais: idle ("Iniciar gravação"), recording (`RecordingIndicator` + botão "Parar"), uploading ("Transcrevendo..."), result (`TranscriptionResult` com 2 botões)
12. Permissão de mic negada → Alert destrutivo com mensagem em pt-BR
13. Auto-stop em 30 segundos é visível (timer chega em `00:30 / 00:30` e gravação para sozinha)
14. `TranscriptionResult` tem `Textarea` editável + botões "Salvar como memória" e "Buscar nos briefings"
15. "Salvar como memória" → toast de sucesso/erro via Sonner; modal fecha em sucesso
16. "Buscar nos briefings" → `navigate("/briefings?q=<texto>")`; modal fecha
17. `BriefingTTSButton` na `BriefingDetailPage` lê o `content` (com markdown removido) usando `SpeechSynthesis`
18. TTS toca em `lang="pt-BR"` quando voz pt está disponível, fallback para default
19. Estados do TTS — botões corretos para idle (Ouvir), speaking (Pausar + Parar), paused (Continuar + Parar)
20. Se `speechSynthesis` não está disponível no browser, `BriefingTTSButton` renderiza `null` (graceful degradation)
21. `npm run build` em `frontend/` zero erros TypeScript e zero warnings de `tsc`
22. `npm test` (`vitest run`) passa todos os smoke tests existentes (6) + os 3 novos da 6b → mínimo 9 verdes

### Estilo
23. Toda primitiva visual vem de `@/components/ui/` (shadcn) — incluindo `dialog`, `textarea`, `alert` recém-adicionados
24. Nenhuma biblioteca de áudio de terceiros (RecordRTC, mic-recorder, wavesurfer, etc.)
25. Nenhuma biblioteca de TTS de terceiros (apenas `SpeechSynthesis` nativo)
26. Cores via tokens shadcn — exceção: indicador de gravação usa `bg-red-500` literal (apropriado para "rec light")
27. Toda página/dialog com requisições de servidor tem estados loading/empty/error onde aplicável

---

## Restrições / O que NÃO entra

- **Sem nova migration Alembic** — sem nova tabela. Telemetria de voz fica em logger
- **Sem persistência de transcrições** — efêmeras, exceto quando usuário clica "Salvar como memória"
- **Sem TTS fora de `BriefingDetailPage`**
- **Sem voz nas páginas Login/Dashboard/Settings**
- **Sem upload de arquivo (drag & drop, file picker)** — apenas mic
- **Sem visualização de waveform** — apenas pulse + timer
- **Sem mobile (<768px)** — desktop e tablet
- **Sem libs externas de áudio/TTS**
- **Não tocar em** `app/services/memory.py`, `app/services/embeddings.py`, `app/routers/mcp.py`, `app/routers/auth.py`, `app/routers/briefings.py`, `app/routers/status.py`, `app/models/*`, `alembic/versions/*`
- **Não modificar** `frontend/src/components/AppShell.tsx`, `frontend/src/auth/*`, `frontend/src/theme/*`, `frontend/src/pages/{Login,Dashboard,BriefingsList,Settings}Page.tsx`. **Apenas TopBar e BriefingDetailPage** ganham a integração
- **Não otimizar performance do frontend** (code splitting de Recharts, etc.) — fica para Fase 6c

---

## Estratégia de testes

### Backend
- Mocks com `unittest.mock.AsyncMock` + `httpx` mockado via `respx` ou `unittest.mock.patch`
- `app.dependency_overrides[get_current_user]` para mockar usuário autenticado (padrão da 6a)
- **Não fazer chamadas reais à Groq** — `transcribe_audio` é mockado nos testes do endpoint
- Reaproveitar fixtures existentes em `tests/conftest.py`

### Frontend
- Mockar `MediaRecorder`, `getUserMedia` e `speechSynthesis` no `setup.ts` global
- Mockar hooks (`useVoiceRecorder`, `useTranscribe`, `useSpeechSynthesis`) nos testes de componente quando precisar de estados específicos
- **Sem testes E2E** — testar manualmente em Chrome e Firefox em dev:
  1. Conceder permissão de mic
  2. Gravar 5s, parar manualmente, verificar transcrição (com `GROQ_API_KEY` válido)
  3. Gravar e deixar bater 30s, verificar auto-stop
  4. Negar permissão, verificar mensagem de erro
  5. Clicar "Salvar como memória" e verificar via `recall_memory` MCP que apareceu
  6. Clicar "Buscar nos briefings" com texto que casa, verificar que filtro funciona
  7. Em `BriefingDetailPage`, clicar "Ouvir resumo" e verificar áudio + estados play/pause/stop

---

## Estrutura sugerida — arquivos novos e modificados

### Backend

| Arquivo | Tipo | Issue |
|---|---|---|
| `app/config.py` | MOD | 6b.B.1 (4 settings novas) |
| `app/services/groq_voice.py` | NOVO | 6b.B.1 |
| `app/routers/voice.py` | NOVO | 6b.B.2 |
| `app/routers/memories.py` | NOVO | 6b.B.3 |
| `app/schemas/memory.py` | NOVO | 6b.B.3 |
| `app/main.py` | MOD | registrar `voice.router` + `memories.router` |
| `tests/test_voice_transcribe.py` | NOVO | 6b.B.4 (6 testes) |
| `tests/test_groq_voice.py` | NOVO | 6b.B.4 (3 testes) |
| `tests/test_memories_create.py` | NOVO | 6b.B.4 (5 testes) |

### Frontend

| Arquivo | Tipo | Issue |
|---|---|---|
| `frontend/src/lib/api.ts` | MOD | 6b.F.2 (postMultipart) |
| `frontend/src/lib/stripMarkdown.ts` | NOVO | 6b.F.4 |
| `frontend/src/hooks/useVoiceRecorder.ts` | NOVO | 6b.F.3 |
| `frontend/src/hooks/useTranscribe.ts` | NOVO | 6b.F.3 |
| `frontend/src/hooks/useCreateMemory.ts` | NOVO | 6b.F.3 |
| `frontend/src/hooks/useSpeechSynthesis.ts` | NOVO | 6b.F.3 |
| `frontend/src/components/voice/MicButton.tsx` | NOVO | 6b.F.4 |
| `frontend/src/components/voice/VoiceCaptureDialog.tsx` | NOVO | 6b.F.4 |
| `frontend/src/components/voice/RecordingIndicator.tsx` | NOVO | 6b.F.4 |
| `frontend/src/components/voice/TranscriptionResult.tsx` | NOVO | 6b.F.4 |
| `frontend/src/components/BriefingTTSButton.tsx` | NOVO | 6b.F.4 |
| `frontend/src/components/TopBar.tsx` | MOD | adicionar `<MicButton />` |
| `frontend/src/pages/BriefingDetailPage.tsx` | MOD | adicionar `<BriefingTTSButton content={...} />` |
| `frontend/src/components/ui/dialog.tsx` | NOVO | shadcn add |
| `frontend/src/components/ui/textarea.tsx` | NOVO | shadcn add |
| `frontend/src/__tests__/setup.ts` | MOD | mocks de MediaRecorder + speechSynthesis |
| `frontend/src/__tests__/MicButton.test.tsx` | NOVO | 6b.F.5 |
| `frontend/src/__tests__/VoiceCaptureDialog.test.tsx` | NOVO | 6b.F.5 |
| `frontend/src/__tests__/BriefingTTSButton.test.tsx` | NOVO | 6b.F.5 |

Total backend: 6 novos + 2 modificados. Total frontend: 13 novos + 3 modificados.

---

## Instrução global de documentação

Seguir o mesmo padrão das Fases 4–6a: gerar bloco "Explicação — Tarefa X.Y" para cada tarefa concluída, com arquivos, trechos relevantes, justificativa e invariantes.

---

## Observação para o KIRO

Esta fase tem **risco moderado de divergência**. Erros comuns que o auditor já viu na 6a:

1. **Improvisar componentes** — desenhar dialog/textarea próprios em vez de usar shadcn. NÃO faça isso. Use `npx shadcn@latest add dialog textarea` na Tarefa 1 do frontend.
2. **Esquecer estados loading/empty/error** — `VoiceCaptureDialog` precisa cobrir 5 estados (idle, recording, uploading, result, error). Use o switch de exemplo do briefing.
3. **Inventar libs** — sem RecordRTC, sem mic-recorder, sem wavesurfer, sem tts-react. Apenas `MediaRecorder` e `SpeechSynthesis` nativos.
4. **Persistir áudio ou transcrição em DB** — explicitamente proibido. Apenas log estruturado sem conteúdo.
5. **Mexer em arquivos fora do escopo** — backend muda apenas `config.py` e `main.py` (registro de routers); frontend muda apenas `TopBar.tsx`, `BriefingDetailPage.tsx`, `setup.ts`. Tudo o resto é arquivo NOVO.
6. **Pular tipos TypeScript** — interfaces de `VoiceTranscriptionResponse`, `MemoryResponse`, etc. devem estar declaradas. Sem `any`.
7. **Não rodar `pytest` completo** — após cada tarefa de backend, `pytest` sem flags. Reportar contagem absoluta. Meta cumulativa final: **164 baseline + 14 novos = 178 verdes**.
8. **TTS sem cancelamento ao desmontar** — `useSpeechSynthesis` faz cleanup no unmount. Não esquecer.
9. **Áudio com Content-Type errado** — não setar `Content-Type` manualmente em FormData; o browser cuida do boundary.

**Ordem sugerida das tarefas:**

1. Tarefa 1: Backend — `groq_voice.py` + settings + 3 testes (6b.B.1, 6b.B.4 parcial)
2. Tarefa 2: Backend — `POST /voice/transcribe` + schemas + 6 testes + registro em main (6b.B.2, 6b.B.4 parcial)
3. Tarefa 3: Backend — `POST /memories` + schemas + 4 testes + registro em main (6b.B.3, 6b.B.4 parcial)
4. Tarefa 4: Frontend — setup (shadcn add dialog textarea) + `lib/api.ts` postMultipart + `lib/stripMarkdown.ts`
5. Tarefa 5: Frontend — hooks (`useVoiceRecorder`, `useTranscribe`, `useCreateMemory`, `useSpeechSynthesis`) + mocks de setup
6. Tarefa 6: Frontend — componentes voice/ + integração na TopBar
7. Tarefa 7: Frontend — `BriefingTTSButton` + integração no `BriefingDetailPage`
8. Tarefa 8: Frontend — 3 smoke tests + `npm run build` limpo + `npm test` verde
9. Checkpoint final — Suíte completa backend + frontend, verificar escopo, sem migrations

**Comece gerando a spec em `.kiro/specs/lanez-fase6b-voz/` (`design.md`, `requirements.md`, `tasks.md`)** seguindo o formato das fases anteriores. Apresente a spec para aprovação antes de implementar.
