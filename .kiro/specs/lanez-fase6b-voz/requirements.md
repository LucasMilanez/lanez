# Documento de Requisitos — Lanez Fase 6b: Voz (STT via Groq Whisper + TTS via SpeechSynthesis)

## Introdução

A Fase 6b do Lanez adiciona dois recursos de voz ao painel React entregue na Fase 6a: (1) captura de voz por microfone com transcrição via Groq Whisper e ações sobre o texto transcrito (salvar como memória ou buscar nos briefings), e (2) leitura por TTS de briefings usando SpeechSynthesis nativo do browser. O backend recebe 3 mudanças: cliente Groq Whisper (`app/services/groq_voice.py`), endpoint `POST /voice/transcribe` (`app/routers/voice.py`), e endpoint REST `POST /memories` (`app/routers/memories.py`). O frontend recebe 4 hooks de voz, 5 componentes novos (4 em `components/voice/` + `BriefingTTSButton`), utilitário `stripMarkdown`, extensão do cliente API com `postMultipart`, e integração na TopBar e BriefingDetailPage. Não há novas migrations, não há nova tabela de telemetria, não há persistência de transcrições.

### Divergências de modelo detectadas (pré-flight)

Antes de redigir os requisitos, os modelos reais foram inspecionados. Divergências encontradas em relação ao briefing original:

| Divergência | Modelo Real | Impacto nos Requisitos |
|---|---|---|
| `save_memory` é função standalone, NÃO método de classe | `async def save_memory(db, user_id, content, tags=None) -> dict` em `app/services/memory.py` — não existe `MemoryService` | Router `POST /memories` deve importar `from app.services.memory import save_memory` e chamar `await save_memory(db=db, user_id=user.id, content=body.content, tags=body.tags)` diretamente |
| Não existe classe `MemoryService` | O briefing assume `MemoryService().save_memory(...)` mas o código real é uma função de módulo | Ajustar chamada no router para a assinatura real |
| Retorno de `save_memory` é `dict`, não ORM object | Retorna `{"id": str(memory.id), "content": memory.content, "tags": memory.tags, "created_at": memory.created_at.isoformat()}` | `MemoryResponse` com `from_attributes=True` não funciona diretamente — construir `MemoryResponse` a partir do dict retornado |
| Campos de `Memory` confirmados | `id` (UUID), `user_id` (UUID), `content` (Text), `tags` (ARRAY(String)), `vector` (Vector(384)), `created_at` (DateTime), `last_accessed_at` (DateTime \| None) | Campo `tags` com `ARRAY(String)` confirmado ✓ |
| `POST /memories` não existe | Confirmado — nenhum `@router.post` com "memor" nos routers existentes | Criar endpoint novo sem conflito ✓ |
| `GROQ_API_KEY` não está em Settings | Confirmado — `app/config.py` não contém `GROQ_API_KEY` | Adicionar 4 settings novas ✓ |

## Glossário

- **Sistema**: A aplicação backend Lanez construída com FastAPI
- **Painel**: Aplicação frontend React em `frontend/` que consome a API REST do Sistema
- **Groq_Whisper**: Serviço externo de transcrição de áudio (modelo `whisper-large-v3-turbo`) acessado via API REST da Groq
- **STT**: Speech-to-Text — conversão de áudio em texto via Groq Whisper
- **TTS**: Text-to-Speech — conversão de texto em áudio via SpeechSynthesis nativo do browser
- **VoiceCaptureDialog**: Modal Dialog do shadcn/ui que gerencia o fluxo completo de captura de voz: gravação → transcrição → ações
- **MicButton**: Botão na TopBar que abre o VoiceCaptureDialog
- **BriefingTTSButton**: Botão na BriefingDetailPage que lê o conteúdo do briefing via SpeechSynthesis
- **RecordingIndicator**: Componente visual com pulse vermelho e timer MM:SS durante gravação
- **TranscriptionResult**: Componente com Textarea editável e dois botões de ação (salvar memória / buscar briefings)
- **MediaRecorder**: API nativa do browser para captura de áudio via microfone
- **SpeechSynthesis**: API nativa do browser para síntese de voz (TTS)
- **stripMarkdown**: Utilitário em `lib/stripMarkdown.ts` que remove sintaxe Markdown do texto antes de enviar ao TTS
- **GroqTranscriptionError**: Exceção customizada levantada quando a transcrição via Groq falha
- **save_memory**: Função standalone em `app/services/memory.py` que persiste uma memória com embedding — NÃO é método de classe

## Requisitos

### Requisito R1: Cliente Groq Whisper

**User Story:** Como sistema backend, quero um cliente fino para a API Groq Whisper, para que o endpoint de transcrição possa enviar áudio e receber texto transcrito.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/services/groq_voice.py` com função assíncrona `transcribe_audio(audio_bytes: bytes, filename: str, content_type: str) -> str` que envia áudio multipart para a API da Groq e retorna o texto transcrito
2. THE Sistema SHALL adicionar 4 settings novas em `app/config.py`: `GROQ_API_KEY` (str, default=""), `GROQ_WHISPER_MODEL` (str, default="whisper-large-v3-turbo"), `VOICE_MAX_AUDIO_BYTES` (int, default=5*1024*1024), `VOICE_MAX_DURATION_SECONDS` (int, default=30)
3. THE Sistema SHALL criar exceção `GroqTranscriptionError` em `app/services/groq_voice.py` para falhas de transcrição
4. IF `GROQ_API_KEY` estiver vazio, THEN THE Sistema SHALL levantar `GroqTranscriptionError` com mensagem "GROQ_API_KEY não configurado"
5. IF a API Groq retornar status diferente de 200, THEN THE Sistema SHALL levantar `GroqTranscriptionError` com o código de status
6. IF a API Groq retornar texto vazio, THEN THE Sistema SHALL levantar `GroqTranscriptionError` com mensagem "Groq retornou texto vazio"
7. IF ocorrer erro de rede ao chamar a API Groq, THEN THE Sistema SHALL levantar `GroqTranscriptionError` com detalhes do erro
8. THE Sistema SHALL usar `language="pt"` e `response_format="json"` na chamada à API Groq
9. THE Sistema SHALL usar `httpx.AsyncClient` com timeout de 60 segundos para a chamada à API Groq
10. THE Sistema NÃO SHALL logar conteúdo do áudio nem da transcrição — apenas metadados (user_id, bytes, duration_ms)

### Requisito R2: Endpoint POST /voice/transcribe

**User Story:** Como painel React, quero enviar áudio capturado pelo microfone para o backend e receber a transcrição em texto, para que o usuário possa agir sobre o que disse.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/routers/voice.py` com router `APIRouter(prefix="/voice", tags=["voice"])` e endpoint `POST /voice/transcribe` com `response_model=VoiceTranscriptionResponse`
2. THE endpoint SHALL aceitar `multipart/form-data` com campo `audio` do tipo `UploadFile`
3. THE endpoint SHALL validar Content-Type do áudio separando parâmetros antes de comparar — `raw_ct = (audio.content_type or "").split(";")[0].strip()` — para aceitar `audio/webm;codecs=opus` do Chrome
4. THE endpoint SHALL aceitar Content-Types: `audio/webm`, `audio/ogg`, `audio/mp4`, `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/flac`
5. IF o Content-Type não estiver na lista permitida, THEN THE Sistema SHALL retornar HTTP 415 com detail informando o Content-Type recebido
6. IF o tamanho do áudio exceder `VOICE_MAX_AUDIO_BYTES` (5 MB), THEN THE Sistema SHALL retornar HTTP 413 com detail informando o tamanho recebido
7. IF o body do áudio estiver vazio, THEN THE Sistema SHALL retornar HTTP 400 com detail "Áudio vazio"
8. IF a transcrição via Groq falhar (`GroqTranscriptionError`), THEN THE Sistema SHALL retornar HTTP 502 com detail "Falha ao transcrever áudio"
9. THE endpoint SHALL retornar `VoiceTranscriptionResponse` com campos `transcription` (str) e `duration_ms` (int — tempo total da chamada)
10. THE endpoint SHALL usar `Depends(get_current_user)` para autenticação — retorna 401 sem auth
11. THE Sistema SHALL registrar `voice.router` em `app/main.py` junto aos demais routers
12. THE endpoint SHALL logar telemetria mínima via `logger.info` com `user_id`, `bytes` e `duration_ms` — sem áudio, sem transcrição

### Requisito R3: Endpoint REST POST /memories

**User Story:** Como painel React, quero salvar memórias diretamente via REST sem passar pelo MCP JSON-RPC, para que o fluxo de voz possa persistir transcrições como memórias de forma simples.

#### Critérios de Aceitação

1. THE Sistema SHALL criar `app/routers/memories.py` com router `APIRouter(prefix="/memories", tags=["memories"])` e endpoint `POST /memories` com `response_model=MemoryResponse` e `status_code=201`
2. THE Sistema SHALL criar `app/schemas/memory.py` com schemas `MemoryCreateRequest` e `MemoryResponse`
3. THE `MemoryCreateRequest` SHALL ter campo `content` (str, min_length=1, max_length=10_000) e campo `tags` (list[str], default_factory=list, max_length=20)
4. THE `MemoryCreateRequest` SHALL ter `field_validator("content")` que faz strip e rejeita conteúdo apenas whitespace com ValueError
5. THE `MemoryResponse` SHALL ter campos `id` (UUID), `content` (str), `tags` (list[str]), `created_at` (datetime)
6. THE endpoint SHALL chamar `save_memory` como função standalone — `from app.services.memory import save_memory` seguido de `await save_memory(db=db, user_id=user.id, content=body.content, tags=body.tags)` — NÃO como método de classe `MemoryService`
7. THE endpoint SHALL construir `MemoryResponse` a partir do dict retornado por `save_memory` (que retorna `{"id": str, "content": str, "tags": list, "created_at": str}`)
8. THE endpoint SHALL usar `Depends(get_current_user)` para autenticação — retorna 401 sem auth
9. THE Sistema SHALL registrar `memories.router` em `app/main.py` junto aos demais routers
10. THE Sistema NÃO SHALL modificar `app/services/memory.py` — reaproveitar a função existente como está

### Requisito R4: Testes do Backend

**User Story:** Como desenvolvedor, quero testes automatizados cobrindo os novos endpoints e o cliente Groq, para garantir que as mudanças funcionam corretamente e não quebram o sistema existente.

#### Critérios de Aceitação

1. THE Sistema SHALL incluir teste `test_voice_transcribe_returns_text` — mock `transcribe_audio`, verifica 200 + campo `transcription` no body
2. THE Sistema SHALL incluir teste `test_voice_transcribe_rejects_unsupported_content_type` — content-type `application/json` retorna 415
3. THE Sistema SHALL incluir teste `test_voice_transcribe_rejects_oversized_audio` — body > 5 MB retorna 413
4. THE Sistema SHALL incluir teste `test_voice_transcribe_rejects_empty_audio` — body vazio retorna 400
5. THE Sistema SHALL incluir teste `test_voice_transcribe_returns_502_on_groq_failure` — mock `transcribe_audio` levantando `GroqTranscriptionError` retorna 502
6. THE Sistema SHALL incluir teste `test_voice_transcribe_requires_auth` — sem cookie/Bearer retorna 401
7. THE Sistema SHALL incluir teste `test_groq_voice_raises_on_missing_api_key` — settings com key vazia levanta `GroqTranscriptionError`
8. THE Sistema SHALL incluir teste `test_groq_voice_raises_on_non_200_status` — httpx mock retornando 500 levanta `GroqTranscriptionError`
9. THE Sistema SHALL incluir teste `test_groq_voice_raises_on_empty_text` — Groq retorna `{"text": ""}` levanta `GroqTranscriptionError`
10. THE Sistema SHALL incluir teste `test_create_memory_201_with_id_and_created_at` — mock `save_memory` retornando dict, verifica 201 com id e created_at
11. THE Sistema SHALL incluir teste `test_create_memory_validates_min_length` — body com `content=""` retorna 422
12. THE Sistema SHALL incluir teste `test_create_memory_rejects_whitespace_only_content` — body com `content="   "` retorna 422
13. THE Sistema SHALL incluir teste `test_create_memory_validates_max_tags` — body com 21 tags retorna 422
14. THE Sistema SHALL incluir teste `test_create_memory_requires_auth` — sem cookie/Bearer retorna 401
15. THE suíte completa de testes (164 existentes + 14 novos = 178) SHALL passar sem flags `-k` ou `-x`

### Requisito R5: Setup Frontend e Utilitários

**User Story:** Como desenvolvedor do frontend, quero os componentes shadcn necessários instalados e os utilitários base criados, para que o desenvolvimento dos componentes de voz possa começar com a infraestrutura correta.

#### Critérios de Aceitação

1. THE Painel SHALL adicionar componentes shadcn/ui `dialog` e `textarea` via `npx shadcn@latest add dialog textarea`
2. THE Painel SHALL modificar `frontend/vite.config.ts` adicionando proxy para `/voice` e `/memories` apontando para `http://localhost:8000`
3. THE Painel SHALL adicionar função `requestMultipart<T>(path: string, formData: FormData): Promise<T>` em `frontend/src/lib/api.ts` — NÃO setar Content-Type manualmente (browser gera boundary correto)
4. THE Painel SHALL expor `postMultipart` no objeto `api` exportado de `frontend/src/lib/api.ts`
5. THE Painel SHALL criar `frontend/src/lib/stripMarkdown.ts` com função `stripMarkdown(md: string): string` que remove headers, bold/italic, inline code, code fences, links, bullets, numbered lists, blockquotes e tabelas
6. THE função `stripMarkdown` SHALL incluir regra para blockquotes (`> texto`) — obrigatório para evitar que TTS leia "maior que"

### Requisito R6: Hooks de Voz

**User Story:** Como desenvolvedor do frontend, quero hooks React encapsulando MediaRecorder, transcrição, criação de memória e SpeechSynthesis, para que os componentes de voz possam consumir essas funcionalidades de forma declarativa.

#### Critérios de Aceitação

1. THE Painel SHALL criar `frontend/src/hooks/useVoiceRecorder.ts` encapsulando `MediaRecorder` com estados: `idle`, `requesting-permission`, `recording`, `stopping`, `error`
2. THE hook `useVoiceRecorder` SHALL expor: `state`, `errorMessage`, `elapsedSeconds`, `start()`, `stop()`, `reset()`
3. THE hook `useVoiceRecorder` SHALL implementar auto-stop em 30 segundos via `useEffect` separado observando `elapsedSeconds` — NÃO dentro do state updater do tick
4. THE hook `useVoiceRecorder` SHALL tratar `NotAllowedError` com mensagem em pt-BR: "Permissão de microfone negada. Habilite nas configurações do navegador."
5. THE função `reset()` SHALL chamar `MediaRecorder.stop()` se `state === "recording"` antes de fazer cleanup de timer e stream
6. THE Painel SHALL criar `frontend/src/hooks/useTranscribe.ts` como TanStack mutation para `POST /voice/transcribe` usando `api.postMultipart`
7. THE Painel SHALL criar `frontend/src/hooks/useCreateMemory.ts` como TanStack mutation para `POST /memories` usando `api.post`
8. THE Painel SHALL criar `frontend/src/hooks/useSpeechSynthesis.ts` encapsulando `SpeechSynthesis` com estados: `idle`, `speaking`, `paused`
9. THE hook `useSpeechSynthesis` SHALL disparar `getVoices()` no mount e ouvir evento `voiceschanged` via `useEffect` para garantir disponibilidade de voz pt-BR na primeira chamada
10. THE hook `useSpeechSynthesis` SHALL cancelar síntese no unmount via cleanup do `useEffect`
11. THE hook `useSpeechSynthesis` SHALL usar `lang="pt-BR"` e buscar voz pt disponível via `getVoices().find(v => v.lang.startsWith("pt"))`

### Requisito R7: Componentes de Voz e Integração na TopBar

**User Story:** Como usuário do painel, quero um botão de microfone na barra superior que abre um modal de captura de voz com gravação, transcrição e ações, para que eu possa interagir com o sistema por voz.

#### Critérios de Aceitação

1. THE Painel SHALL criar `frontend/src/components/voice/MicButton.tsx` com botão `variant="ghost" size="icon"` e ícone `Mic` do lucide-react que abre o VoiceCaptureDialog
2. THE Painel SHALL criar `frontend/src/components/voice/VoiceCaptureDialog.tsx` usando `Dialog` do shadcn/ui com 4 estados visuais: idle ("Iniciar gravação"), recording (RecordingIndicator + botão "Parar"), uploading ("Transcrevendo..."), result (TranscriptionResult)
3. THE Painel SHALL criar `frontend/src/components/voice/RecordingIndicator.tsx` com pulse vermelho (`bg-red-500 animate-pulse`) e timer no formato `MM:SS / MM:SS` com `padStart(2, "0")` em AMBOS os lados (minutos E segundos)
4. THE Painel SHALL criar `frontend/src/components/voice/TranscriptionResult.tsx` com `Textarea` editável do shadcn/ui e dois botões: "Salvar como memória" e "Buscar nos briefings"
5. WHEN o usuário clica "Salvar como memória", THEN THE Painel SHALL chamar `POST /memories` com `tags: ["voz"]`, exibir toast de sucesso via Sonner e fechar o modal
6. WHEN o usuário clica "Buscar nos briefings", THEN THE Painel SHALL navegar para `/briefings?q=<texto>` e fechar o modal
7. IF a permissão de microfone for negada, THEN THE VoiceCaptureDialog SHALL exibir `Alert variant="destructive"` com mensagem em pt-BR
8. THE Painel SHALL modificar `frontend/src/components/TopBar.tsx` para incluir `<MicButton />` à esquerda do `<ThemeToggle />` — sem alterar mais nada na TopBar
9. WHEN a gravação atinge 30 segundos, THEN THE VoiceCaptureDialog SHALL parar automaticamente (timer mostra `00:30 / 00:30`)
10. THE `TranscriptionResult` SHALL importar `useState` de `"react"`, NÃO usar `React.useState`

### Requisito R8: BriefingTTSButton e TTS

**User Story:** Como usuário do painel, quero ouvir o conteúdo de um briefing lido em voz alta pelo navegador, para que eu possa consumir briefings sem precisar ler a tela.

#### Critérios de Aceitação

1. THE Painel SHALL criar `frontend/src/components/BriefingTTSButton.tsx` (NÃO dentro de `voice/`) que usa `useSpeechSynthesis` e `stripMarkdown`
2. THE BriefingTTSButton SHALL exibir 3 estados de botão: idle ("Ouvir resumo" com ícone Play), speaking ("Pausar" + "Parar" com ícones Pause e StopCircle), paused ("Continuar" + "Parar" com ícones Play e StopCircle)
3. IF `speechSynthesis` não estiver disponível no browser, THEN THE BriefingTTSButton SHALL renderizar `null` (graceful degradation)
4. THE BriefingTTSButton SHALL usar `stripMarkdown(content)` antes de enviar texto ao SpeechSynthesis
5. THE Painel SHALL modificar `frontend/src/pages/BriefingDetailPage.tsx` para incluir `<BriefingTTSButton content={briefing.content} />` — sem reescrever a página inteira
6. THE TTS SHALL usar `lang="pt-BR"` quando voz pt estiver disponível, com fallback para voz default do browser

### Requisito R9: Testes do Frontend

**User Story:** Como desenvolvedor, quero smoke tests para os novos componentes de voz, para garantir que renderizam corretamente e que os mocks de MediaRecorder e SpeechSynthesis funcionam.

#### Critérios de Aceitação

1. THE Painel SHALL modificar `frontend/src/__tests__/setup.ts` adicionando mocks globais para `MediaRecorder`, `navigator.mediaDevices.getUserMedia`, `window.speechSynthesis` (incluindo `addEventListener`/`removeEventListener`) e `SpeechSynthesisUtterance`
2. THE Painel SHALL criar `frontend/src/__tests__/MicButton.test.tsx` verificando que clicar no botão abre o dialog
3. THE Painel SHALL criar `frontend/src/__tests__/VoiceCaptureDialog.test.tsx` verificando que render inicial mostra botão "Iniciar gravação" e que estado error mostra Alert
4. THE Painel SHALL criar `frontend/src/__tests__/BriefingTTSButton.test.tsx` verificando que `supported: false` renderiza null e que `state === "speaking"` mostra botões "Pausar" e "Parar"
5. THE Painel SHALL passar `npm run build` (`tsc && vite build`) com zero erros TypeScript e zero warnings
6. THE Painel SHALL passar `npm test` (`vitest run`) com todos os smoke tests existentes (6) + 3 novos = mínimo 9 verdes

### Requisito NF1: Restrições de Escopo — Sem Migrations

**User Story:** Como desenvolvedor, quero garantir que esta fase não introduza migrations de banco nem tabelas novas, para manter a estabilidade do schema existente.

#### Critérios de Aceitação

1. THE Sistema NÃO SHALL criar novas migrations Alembic — sem nova tabela de telemetria de voz
2. THE Sistema NÃO SHALL modificar arquivos em `app/models/*`, `app/services/memory.py`, `app/services/embeddings.py`, `app/routers/mcp.py`, `app/routers/auth.py`, `app/routers/briefings.py`, `app/routers/status.py`, `alembic/versions/*`
3. THE Sistema NÃO SHALL persistir áudio nem transcrições em banco de dados — apenas log estruturado sem conteúdo

### Requisito NF2: Restrições de Bibliotecas

**User Story:** Como desenvolvedor, quero garantir que o frontend use exclusivamente APIs nativas do browser para áudio e TTS, sem bibliotecas de terceiros.

#### Critérios de Aceitação

1. THE Painel NÃO SHALL usar bibliotecas de áudio de terceiros (RecordRTC, mic-recorder, wavesurfer, etc.) — apenas `MediaRecorder` nativo
2. THE Painel NÃO SHALL usar bibliotecas de TTS de terceiros — apenas `SpeechSynthesis` nativo
3. THE Painel SHALL usar exclusivamente primitivos do shadcn/ui para componentes visuais — incluindo `dialog`, `textarea`, `alert`
4. THE Painel NÃO SHALL modificar `frontend/src/components/AppShell.tsx`, `frontend/src/auth/*`, `frontend/src/theme/*`, `frontend/src/pages/{Login,Dashboard,BriefingsList,Settings}Page.tsx` — apenas TopBar e BriefingDetailPage recebem integração

### Requisito NF3: Integridade da Suíte de Testes

**User Story:** Como desenvolvedor, quero que a suíte completa de testes continue verde após as mudanças, para garantir que nenhuma funcionalidade existente foi quebrada.

#### Critérios de Aceitação

1. THE suíte de testes backend SHALL manter os 164 testes existentes verdes mais 14 novos = 178 verdes (6 voice + 3 groq + 5 memories)
2. THE suíte SHALL ser executada com `pytest` sem flags `-k` ou `-x` — todos os testes devem passar
3. THE suíte de testes frontend SHALL manter os 6 smoke tests existentes verdes mais 3 novos = mínimo 9 verdes

### Requisito NF4: Limites de Áudio

**User Story:** Como sistema, quero impor limites rígidos de duração e tamanho de áudio tanto no client quanto no server, para evitar uploads grandes e custos desnecessários.

#### Critérios de Aceitação

1. THE Sistema SHALL limitar tamanho de áudio a 5 MB no server (`VOICE_MAX_AUDIO_BYTES`)
2. THE Painel SHALL limitar duração de gravação a 30 segundos no client com auto-stop
3. THE Sistema SHALL configurar `VOICE_MAX_DURATION_SECONDS = 30` em settings (para referência, sem validação de duração no server — validação é por tamanho)
