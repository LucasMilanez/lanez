# Tarefas de Implementação — Lanez Fase 6b: Voz (STT via Groq Whisper + TTS via SpeechSynthesis)

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

## Tarefa 1: Backend — Cliente Groq Whisper (`groq_voice.py`) + Settings + 3 testes

- [x] 1.1 Pré-flight — confirmar achados do modelo real antes de prosseguir. Reportar no bloco de explicação:
  - Campos reais de `Memory`: `id` (UUID), `user_id` (UUID), `content` (Text), `tags` (ARRAY(String)), `vector` (Vector(384)), `created_at` (DateTime), `last_accessed_at` (DateTime | None) ✓
  - `save_memory` é função standalone `async def save_memory(db, user_id, content, tags=None) -> dict` — NÃO existe classe `MemoryService`
  - Retorno de `save_memory` é `dict`: `{"id": str(memory.id), "content": memory.content, "tags": memory.tags, "created_at": memory.created_at.isoformat()}`
  - `POST /memories` NÃO existe ainda ✓
  - `GROQ_API_KEY` NÃO está em Settings ainda ✓
  - _Requisitos: R1.2, R3.6, R3.7_

- [x] 1.2 Adicionar 4 settings novas em `app/config.py`: `GROQ_API_KEY: str = ""`, `GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"`, `VOICE_MAX_AUDIO_BYTES: int = 5 * 1024 * 1024`, `VOICE_MAX_DURATION_SECONDS: int = 30`. Adicionar ANTES de `model_config`
  - _Requisitos: R1.2_

- [x] 1.3 Criar `app/services/groq_voice.py` com:
  - Constantes: `GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"`, `_HTTP_TIMEOUT = 60.0`
  - Exceção `GroqTranscriptionError(Exception)`
  - Função `async def transcribe_audio(audio_bytes: bytes, filename: str, content_type: str) -> str`
  - Validação: se `settings.GROQ_API_KEY` vazio → `GroqTranscriptionError("GROQ_API_KEY não configurado")`
  - Chamada: `httpx.AsyncClient(timeout=_HTTP_TIMEOUT)` com `files={"file": (filename, audio_bytes, content_type)}`, `data={"model": settings.GROQ_WHISPER_MODEL, "language": "pt", "response_format": "json"}`, `headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}`
  - Tratamento: status != 200 → `GroqTranscriptionError(f"Groq retornou {resp.status_code}")`, texto vazio → `GroqTranscriptionError("Groq retornou texto vazio")`, erro de rede → `GroqTranscriptionError(f"Erro de rede: {e}")`
  - Logger NÃO loga conteúdo do áudio nem da transcrição
  - _Requisitos: R1.1, R1.3, R1.4, R1.5, R1.6, R1.7, R1.8, R1.9, R1.10_

- [x] 1.4 Criar `tests/test_groq_voice.py` com 3 testes:
  - `test_groq_voice_raises_on_missing_api_key` — mock settings com `GROQ_API_KEY=""` → `GroqTranscriptionError`
  - `test_groq_voice_raises_on_non_200_status` — mock httpx retornando status 500 → `GroqTranscriptionError`
  - `test_groq_voice_raises_on_empty_text` — mock httpx retornando `{"text": ""}` → `GroqTranscriptionError`
  - _Requisitos: R4.7, R4.8, R4.9_

- [x] 1.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed". Meta: 164 existentes + 3 novos = 167 verdes
  - _Requisitos: R4.15, NF3.1, NF3.2_

## Tarefa 2: Backend — POST /voice/transcribe + schemas + 6 testes + registro em main

- [x] 2.1 Criar `app/routers/voice.py` com:
  - Router: `APIRouter(prefix="/voice", tags=["voice"])`
  - Schema inline: `VoiceTranscriptionResponse(BaseModel)` com `transcription: str` e `duration_ms: int`
  - Constante: `_ALLOWED_CONTENT_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/flac"}`
  - Endpoint `POST /transcribe` com `response_model=VoiceTranscriptionResponse`
  - Parâmetros: `audio: UploadFile = File(...)`, `user: User = Depends(get_current_user)`
  - Validação Content-Type: `raw_ct = (audio.content_type or "").split(";")[0].strip()` — aceita `audio/webm;codecs=opus` do Chrome
  - Validação tamanho: `len(audio_bytes) > settings.VOICE_MAX_AUDIO_BYTES` → 413
  - Validação vazio: `not audio_bytes` → 400
  - Chamada: `transcribe_audio(audio_bytes, audio.filename or "audio.webm", raw_ct)`
  - Catch `GroqTranscriptionError` → 502 "Falha ao transcrever áudio"
  - Telemetria: `logger.info("voice.transcribe user_id=%s bytes=%d duration_ms=%d", ...)` — sem áudio, sem transcrição
  - _Requisitos: R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R2.7, R2.8, R2.9, R2.10, R2.12_

- [x] 2.2 Registrar router em `app/main.py`: `from app.routers.voice import router as voice_router` + `app.include_router(voice_router)`
  - _Requisitos: R2.11_

- [x] 2.3 Criar `tests/test_voice_transcribe.py` com 6 testes:
  - `test_voice_transcribe_returns_text` — mock `transcribe_audio` retornando "texto teste", envia multipart com `audio/webm`, verifica 200 + `transcription == "texto teste"` + `duration_ms` presente
  - `test_voice_transcribe_rejects_unsupported_content_type` — content-type `application/json` → 415
  - `test_voice_transcribe_rejects_oversized_audio` — body com > 5 MB → 413
  - `test_voice_transcribe_rejects_empty_audio` — body vazio (0 bytes) → 400
  - `test_voice_transcribe_returns_502_on_groq_failure` — mock `transcribe_audio` levantando `GroqTranscriptionError("falha")` → 502
  - `test_voice_transcribe_requires_auth` — sem cookie/Bearer → 401
  - Usar `app.dependency_overrides[get_current_user]` para mockar usuário autenticado (padrão 6a)
  - Usar `unittest.mock.patch("app.routers.voice.transcribe_audio")` para mockar a função
  - _Requisitos: R4.1, R4.2, R4.3, R4.4, R4.5, R4.6_

- [x] 2.4 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed". Meta: 167 + 6 = 173 verdes
  - _Requisitos: R4.15, NF3.1, NF3.2_

## Tarefa 3: Backend — POST /memories + schemas + 5 testes + registro em main

- [x] 3.1 Criar `app/schemas/memory.py` com:
  - `MemoryCreateRequest(BaseModel)`: `content: str = Field(..., min_length=1, max_length=10_000)`, `tags: list[str] = Field(default_factory=list, max_length=20)`
  - `field_validator("content")` que faz `v.strip()` e rejeita whitespace-only com `ValueError("content não pode ser apenas whitespace")`
  - `MemoryResponse(BaseModel)`: `id: UUID`, `content: str`, `tags: list[str]`, `created_at: datetime`
  - **NÃO** usar `from_attributes=True` em `MemoryResponse` — o retorno de `save_memory` é dict, não ORM
  - _Requisitos: R3.2, R3.3, R3.4, R3.5_

- [x] 3.2 Criar `app/routers/memories.py` com:
  - Router: `APIRouter(prefix="/memories", tags=["memories"])`
  - Endpoint `POST ""` com `response_model=MemoryResponse`, `status_code=201`
  - Parâmetros: `body: MemoryCreateRequest`, `user: User = Depends(get_current_user)`, `db: AsyncSession = Depends(get_db)`
  - Importar `from app.services.memory import save_memory` — função standalone, NÃO classe
  - Chamar: `result = await save_memory(db=db, user_id=user.id, content=body.content, tags=body.tags)`
  - Construir `MemoryResponse` a partir do dict retornado: `MemoryResponse(id=result["id"], content=result["content"], tags=result["tags"], created_at=result["created_at"])`
  - _Requisitos: R3.1, R3.6, R3.7, R3.8, R3.10_

- [x] 3.3 Registrar router em `app/main.py`: `from app.routers.memories import router as memories_router` + `app.include_router(memories_router)`
  - _Requisitos: R3.9_

- [x] 3.4 Criar `tests/test_memories_create.py` com 5 testes:
  - `test_create_memory_201_with_id_and_created_at` — mock `save_memory` retornando dict `{"id": "uuid-str", "content": "teste", "tags": ["voz"], "created_at": "2024-01-15T10:30:00+00:00"}`, verifica 201 com `id` e `created_at` presentes
  - `test_create_memory_validates_min_length` — body com `content=""` → 422
  - `test_create_memory_rejects_whitespace_only_content` — body com `content="   "` → 422 (validator de strip)
  - `test_create_memory_validates_max_tags` — body com 21 tags → 422
  - `test_create_memory_requires_auth` — sem cookie/Bearer → 401
  - Usar `app.dependency_overrides[get_current_user]` e `unittest.mock.patch("app.routers.memories.save_memory")` para mocks
  - _Requisitos: R4.10, R4.11, R4.12, R4.13, R4.14_

- [x] 3.5 Rodar `pytest` completo (sem `-k`, sem `-x`). Reportar contagem "N passed, M failed". Meta: 173 + 5 = **178 verdes** (meta final backend)
  - _Requisitos: R4.15, NF3.1, NF3.2_

## Tarefa 4: Frontend — Setup (shadcn dialog + textarea) + lib/api.ts postMultipart + lib/stripMarkdown.ts

**Dependência:** Tarefas 1–3 (backend) devem estar completas e testadas antes de iniciar frontend.

- [x] 4.1 Adicionar componentes shadcn/ui: executar `npx shadcn@latest add dialog textarea` em `frontend/`. Verificar que `frontend/src/components/ui/dialog.tsx` e `frontend/src/components/ui/textarea.tsx` foram criados
  - _Requisitos: R5.1_

- [x] 4.2 Modificar `frontend/vite.config.ts` — adicionar proxy para `/voice` e `/memories` apontando para `http://localhost:8000`:
  - `"/voice": "http://localhost:8000"` com comentário `// Fase 6b`
  - `"/memories": "http://localhost:8000"` com comentário `// Fase 6b`
  - NÃO alterar proxies existentes (`/auth`, `/briefings`, `/status`, `/mcp`)
  - _Requisitos: R5.2_

- [x] 4.3 Modificar `frontend/src/lib/api.ts` — adicionar função `requestMultipart<T>(path: string, formData: FormData): Promise<T>`:
  - Usar `fetch(path, { method: "POST", body: formData, credentials: "include" })` — NÃO setar Content-Type manualmente
  - Tratar 204 retornando `undefined as T`
  - Tratar erros com `ApiError(response.status, detail)`
  - Expor `postMultipart` no objeto `api` exportado
  - NÃO substituir métodos existentes (`get`, `post`)
  - _Requisitos: R5.3, R5.4_

- [x] 4.4 Criar `frontend/src/lib/stripMarkdown.ts` com função `stripMarkdown(md: string): string`:
  - Remover: headers (`^#{1,6}\s+`), bold/italic (`**`, `*`, `__`, `_`), inline code (`` ` ``), code fences (` ``` `), links (`[texto](url)` → texto), bullets (`^[-*+]\s+`), numbered lists (`^\d+\.\s+`), blockquotes (`^>\s+` — OBRIGATÓRIO), tabelas (pipes e separadores), múltiplas quebras
  - _Requisitos: R5.5, R5.6_

- [x] 4.5 Verificar que `npm run build` em `frontend/` passa sem erros TypeScript
  - _Requisitos: R9.5_

## Tarefa 5: Frontend — Hooks (useVoiceRecorder, useTranscribe, useCreateMemory, useSpeechSynthesis) + mocks setup.ts

**Dependência:** Tarefa 4 (setup frontend) deve estar completa.

- [x] 5.1 Criar `frontend/src/hooks/useVoiceRecorder.ts`:
  - Estados: `idle`, `requesting-permission`, `recording`, `stopping`, `error`
  - Expor: `state`, `errorMessage`, `elapsedSeconds`, `start()`, `stop()`, `reset()`
  - `start()`: `getUserMedia({audio: true})` → `new MediaRecorder(stream)` → `recorder.start()` → tick via `setInterval` (apenas incrementa contador)
  - `stop()`: retorna `Promise<Blob | null>` resolvida no callback `onstop`
  - `reset()`: chama `MediaRecorder.stop()` se `state === "recording"` antes de cleanup
  - Auto-stop: `useEffect` separado observando `elapsedSeconds >= 30` — NÃO dentro do state updater
  - Tratamento `NotAllowedError`: mensagem pt-BR "Permissão de microfone negada. Habilite nas configurações do navegador."
  - Cleanup no unmount: timer + stream tracks
  - _Requisitos: R6.1, R6.2, R6.3, R6.4, R6.5_

- [x] 5.2 Criar `frontend/src/hooks/useTranscribe.ts`:
  - TanStack `useMutation<VoiceTranscriptionResponse, ApiError, Blob>`
  - `mutationFn`: cria `FormData`, append `audio` com filename baseado no tipo (`audio.mp4` ou `audio.webm`), chama `api.postMultipart`
  - _Requisitos: R6.6_

- [x] 5.3 Criar `frontend/src/hooks/useCreateMemory.ts`:
  - TanStack `useMutation<MemoryResponse, ApiError, CreateMemoryInput>`
  - `mutationFn`: chama `api.post<MemoryResponse>("/memories", { content, tags })`
  - _Requisitos: R6.7_

- [x] 5.4 Criar `frontend/src/hooks/useSpeechSynthesis.ts`:
  - Estados: `idle`, `speaking`, `paused`
  - Expor: `state`, `speak(text)`, `pause()`, `resume()`, `cancel()`, `supported`
  - `useEffect` no mount: `getVoices()` + `addEventListener("voiceschanged", handler)` — garante voz pt-BR disponível na 1ª chamada
  - `speak()`: `cancel()` → `new SpeechSynthesisUtterance(text)` → `lang="pt-BR"` → busca voz pt → `speak(utter)`
  - Cleanup no unmount: `speechSynthesis.cancel()`
  - _Requisitos: R6.8, R6.9, R6.10, R6.11_

- [x] 5.5 Modificar `frontend/src/__tests__/setup.ts` — adicionar mocks globais:
  - `navigator.mediaDevices` com `getUserMedia: vi.fn()`
  - `global.MediaRecorder` mockado com `start`, `stop`, `state`, `mimeType`
  - `window.speechSynthesis` com `speak`, `cancel`, `pause`, `resume`, `getVoices`, `addEventListener`, `removeEventListener`
  - `global.SpeechSynthesisUtterance` mockado
  - _Requisitos: R9.1_

- [x] 5.6 Verificar que `npm run build` em `frontend/` passa sem erros TypeScript
  - _Requisitos: R9.5_

## Tarefa 6: Frontend — Componentes voice/ + integração na TopBar

**Dependência:** Tarefa 5 (hooks) deve estar completa.

- [x] 6.1 Criar `frontend/src/components/voice/MicButton.tsx`:
  - `Button variant="ghost" size="icon"` com ícone `Mic` do lucide-react
  - `aria-label="Capturar voz"`
  - Estado local `open` para controlar `VoiceCaptureDialog`
  - _Requisitos: R7.1_

- [x] 6.2 Criar `frontend/src/components/voice/RecordingIndicator.tsx`:
  - Props: `elapsedSeconds: number`, `maxSeconds?: number` (default 30)
  - Formato: `MM:SS / MM:SS` com `padStart(2, "0")` em AMBOS os lados (minutos E segundos)
  - Pulse: `span` com `bg-red-500 animate-pulse` (classe `cn()`)
  - _Requisitos: R7.3_

- [x] 6.3 Criar `frontend/src/components/voice/TranscriptionResult.tsx`:
  - Props: `initialText: string`, `onClose: () => void`
  - `Textarea` editável do shadcn/ui com `aria-label="Transcrição editável"`
  - Importar `useState` de `"react"`, NÃO usar `React.useState`
  - Botão "Salvar como memória": `useCreateMemory().mutate({content: text, tags: ["voz"]})` → `toast.success("Memória salva")` + `onClose()`
  - Botão "Buscar nos briefings": `navigate(\`/briefings?q=${encodeURIComponent(text.trim())}\`)` + `onClose()`
  - Ambos botões disabled quando `!text.trim()`
  - _Requisitos: R7.4, R7.5, R7.6, R7.10_

- [x] 6.4 Criar `frontend/src/components/voice/VoiceCaptureDialog.tsx`:
  - `Dialog` do shadcn/ui com `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`
  - 4 estados visuais: idle (botão "Iniciar gravação"), recording (RecordingIndicator + "Parar"), uploading ("Transcrevendo..."), result (TranscriptionResult)
  - Estado error: `Alert variant="destructive"` com `recorder.errorMessage`
  - `handleClose()`: `recorder.reset()` + `transcribe.reset()` + `setTranscription(null)` + `onOpenChange(false)`
  - `handleStop()`: `recorder.stop()` → se blob null → `toast.error("Nenhum áudio capturado")` → senão `transcribe.mutate(blob)`
  - _Requisitos: R7.2, R7.7, R7.9_

- [x] 6.5 Modificar `frontend/src/components/TopBar.tsx` — adicionar `<MicButton />` à esquerda do `<ThemeToggle />`. NÃO alterar mais nada na TopBar. Importar `MicButton` de `@/components/voice/MicButton`
  - _Requisitos: R7.8_

- [x] 6.6 Verificar que `npm run build` em `frontend/` passa sem erros TypeScript
  - _Requisitos: R9.5_

## Tarefa 7: Frontend — BriefingTTSButton + integração no BriefingDetailPage

**Dependência:** Tarefa 5 (hooks — useSpeechSynthesis) deve estar completa.

- [x] 7.1 Criar `frontend/src/components/BriefingTTSButton.tsx` (NÃO dentro de `voice/`):
  - Props: `content: string`
  - Se `!tts.supported` → retorna `null`
  - Estado idle: botão "Ouvir resumo" com ícone `Play` — `onClick={() => tts.speak(stripMarkdown(content))}`
  - Estado speaking: botões "Pausar" (ícone `Pause`) + "Parar" (ícone `StopCircle`)
  - Estado paused: botões "Continuar" (ícone `Play`) + "Parar" (ícone `StopCircle`)
  - Todos os botões `variant="outline" size="sm"`
  - _Requisitos: R8.1, R8.2, R8.3, R8.4, R8.6_

- [x] 7.2 Modificar `frontend/src/pages/BriefingDetailPage.tsx` — adicionar `<BriefingTTSButton content={briefing.content} />` ao lado dos metadados ou logo abaixo do título. NÃO reescrever a página inteira — apenas adicionar o botão e o import
  - _Requisitos: R8.5_

- [x] 7.3 Verificar que `npm run build` em `frontend/` passa sem erros TypeScript
  - _Requisitos: R9.5_

## Tarefa 8: Frontend — 3 smoke tests + npm run build limpo + npm test verde

**Dependência:** Tarefas 6 e 7 (componentes) devem estar completas.

- [x] 8.1 Criar `frontend/src/__tests__/MicButton.test.tsx`:
  - Verificar que clicar no botão abre o dialog (verifica presença de "Captura por voz" ou "Iniciar gravação" após click)
  - Mockar hooks conforme necessário
  - _Requisitos: R9.2_

- [x] 8.2 Criar `frontend/src/__tests__/VoiceCaptureDialog.test.tsx`:
  - Verificar que render inicial com `open=true` mostra botão "Iniciar gravação"
  - Verificar que mockando `useVoiceRecorder` em estado `error` com `errorMessage`, mostra Alert
  - _Requisitos: R9.3_

- [x] 8.3 Criar `frontend/src/__tests__/BriefingTTSButton.test.tsx`:
  - Verificar que quando `useSpeechSynthesis` retorna `supported: false`, componente renderiza `null` (container vazio)
  - Verificar que quando `state === "speaking"`, mostra botões "Pausar" e "Parar"
  - _Requisitos: R9.4_

- [x] 8.4 Rodar `npm run build` (`tsc && vite build`) em `frontend/`. Verificar zero erros TypeScript e zero warnings de `tsc`
  - _Requisitos: R9.5_

- [x] 8.5 Rodar `npm test` (`vitest run`) em `frontend/`. Todos os smoke tests existentes (6) + 3 novos devem passar = mínimo 9 verdes
  - _Requisitos: R9.6, NF3.3_

## Tarefa 9: Checkpoint Final

- [x] 9.1 Rodar `pytest` no backend (sem `-k`, sem `-x`) — meta exata: **178 verdes** (164 baseline + 14 novos: 6 voice + 3 groq + 5 memories)
  - _Requisitos: NF3.1, NF3.2_

- [x] 9.2 Rodar `npm test` no frontend — mínimo **9 verdes** (6 baseline + 3 novos)
  - _Requisitos: NF3.3_

- [x] 9.3 Verificar que nenhum arquivo fora do escopo foi modificado:
  - `app/models/*` — inalterado
  - `app/services/memory.py` — inalterado
  - `app/services/embeddings.py` — inalterado
  - `app/routers/mcp.py` — inalterado
  - `app/routers/auth.py` — inalterado
  - `app/routers/briefings.py` — inalterado
  - `app/routers/status.py` — inalterado
  - `alembic/versions/*` — inalterado
  - `frontend/src/components/AppShell.tsx` — inalterado
  - `frontend/src/auth/*` — inalterado
  - `frontend/src/theme/*` — inalterado
  - `frontend/src/pages/{Login,Dashboard,BriefingsList,Settings}Page.tsx` — inalterado
  - _Requisitos: NF1.2, NF2.4_

- [x] 9.4 Verificar que nenhuma migration Alembic foi criada — `alembic/versions/` deve ter apenas os 4 arquivos existentes (001–004)
  - _Requisitos: NF1.1_

- [x] 9.5 Verificar escopo: apenas os arquivos listados na seção "Estrutura sugerida" do briefing foram criados/modificados. Se houver dúvidas ou falhas, perguntar ao usuário antes de prosseguir
  - _Requisitos: NF1.1, NF1.2, NF1.3_

## Notas

- Tarefas 1–3 são backend e devem ser completadas e testadas antes de iniciar o frontend (Tarefas 4–8)
- Cada tarefa backend termina com execução completa do `pytest` para garantir regressão zero
- Todas as referências a requisitos apontam para o documento `requirements.md` da Fase 6b
- Propriedades formais de corretude estão definidas no documento `design.md` da Fase 6b
- UI fixa em pt-BR — sem internacionalização
- `save_memory` é função standalone — NÃO instanciar `MemoryService()` no router
- `MemoryResponse` é construído a partir de dict — NÃO usar `from_attributes=True`
- Content-Type do áudio deve ser validado com `split(";")[0].strip()` para aceitar `audio/webm;codecs=opus`
- `TranscriptionResult` importa `useState` de `"react"`, NÃO `React.useState`
- `RecordingIndicator` usa `padStart(2, "0")` em AMBOS os lados (minutos E segundos)
- `stripMarkdown` DEVE incluir regra para blockquotes (`> texto`)
- Mocks de `speechSynthesis` no `setup.ts` DEVEM incluir `addEventListener` e `removeEventListener`
