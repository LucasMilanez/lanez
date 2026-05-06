"""Router MCP — expõe ferramentas do Microsoft 365 via JSON-RPC 2.0.

Implementa o protocolo MCP (Model Context Protocol) sobre HTTP,
permitindo que clientes MCP consumam dados do calendário, emails,
OneNote, OneDrive e busca web.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.database import get_db, get_redis
from app.dependencies import get_current_user
from app.models.briefing import Briefing
from app.models.user import User
from app.services.audit import AuditEventType, log_event
from app.services.graph import GraphService
from app.services.searxng import SearXNGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ---------------------------------------------------------------------------
# Protocol Constants (MCP spec 2025-06-18)
# ---------------------------------------------------------------------------

MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "lanez"
SERVER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MCPTool(BaseModel):
    name: str
    description: str
    inputSchema: dict


class MCPCallRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Definição das 5 ferramentas MCP (descriptions fixas — proteção tool poisoning)
# ---------------------------------------------------------------------------

TOOL_GET_CALENDAR_EVENTS = MCPTool(
    name="get_calendar_events",
    description="Busca eventos do calendário do Outlook em um intervalo de datas.",
    inputSchema={
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "Data inicial (YYYY-MM-DD)"},
            "end": {"type": "string", "description": "Data final (YYYY-MM-DD)"},
        },
        "required": ["start", "end"],
    },
)

TOOL_SEARCH_EMAILS = MCPTool(
    name="search_emails",
    description="Busca emails no Outlook por texto livre.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texto de busca"},
            "limit": {
                "type": "integer",
                "description": "Número máximo de resultados (padrão: 10, máximo: 50)",
            },
        },
        "required": ["query"],
    },
)

TOOL_GET_ONENOTE_PAGES = MCPTool(
    name="get_onenote_pages",
    description="Lista páginas do OneNote, opcionalmente filtrando por título.",
    inputSchema={
        "type": "object",
        "properties": {
            "notebook": {"type": "string", "description": "Nome do notebook (opcional)"},
            "query": {
                "type": "string",
                "description": "Filtro por título da página (opcional)",
            },
        },
        "required": [],
    },
)

TOOL_SEARCH_FILES = MCPTool(
    name="search_files",
    description="Busca arquivos no OneDrive por nome ou conteúdo.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texto de busca"},
        },
        "required": ["query"],
    },
)

TOOL_WEB_SEARCH = MCPTool(
    name="web_search",
    description="Busca na web usando SearXNG (motor de busca self-hosted).",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texto de busca"},
        },
        "required": ["query"],
    },
)

TOOL_SEMANTIC_SEARCH = MCPTool(
    name="semantic_search",
    description=(
        "Busca por significado em todos os serviços do Microsoft 365 simultaneamente. "
        "Use quando o usuário quiser encontrar algo sem saber em qual serviço está, "
        "ou quando uma busca por palavra-chave não for suficiente. "
        "Exemplos: 'encontre informações sobre o projeto Alpha', "
        "'o que discutimos com João sobre contratos?'"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Descrição do que você está buscando"},
            "services": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["calendar", "mail", "onenote", "onedrive"],
                },
                "description": "Filtrar por serviços específicos (opcional — padrão: todos)",
            },
            "limit": {
                "type": "integer",
                "description": "Número máximo de resultados (padrão: 10, máximo: 20)",
            },
        },
        "required": ["query"],
    },
)

TOOL_SAVE_MEMORY = MCPTool(
    name="save_memory",
    description=(
        "Salva uma memória persistente que será lembrada em sessões futuras. "
        "Use para registrar decisões, preferências, projetos em andamento e fatos "
        "importantes do usuário. Cada chamada cria uma nova memória (nunca sobrescreve). "
        "Exemplos: 'o usuário prefere respostas em português', "
        "'projeto Alpha tem deadline em março', "
        "'João é o contato principal para contratos'"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Texto da memória a ser salva — decisão, preferência ou fato importante",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags opcionais para categorizar e filtrar memórias (ex: ['preferencia', 'projeto-alpha'])",
            },
        },
        "required": ["content"],
    },
)

TOOL_RECALL_MEMORY = MCPTool(
    name="recall_memory",
    description=(
        "Recupera memórias relevantes para a conversa atual via busca semântica. "
        "Use no início de sessões para carregar contexto, ou quando o usuário "
        "mencionar algo que pode ter sido salvo anteriormente. "
        "Exemplos: 'quais são as preferências do usuário?', "
        "'o que sabemos sobre o projeto Alpha?', "
        "'buscar decisões sobre contratos'"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Descrição do que você está buscando nas memórias",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrar por tags específicas — retorna memórias com PELO MENOS uma tag da lista (filtro OR)",
            },
            "limit": {
                "type": "integer",
                "description": "Número máximo de resultados (padrão: 5, máximo: 20)",
            },
        },
        "required": ["query"],
    },
)

TOOL_GET_BRIEFING = MCPTool(
    name="get_briefing",
    description=(
        "Recupera o briefing automático gerado para um evento de reunião do calendar. "
        "O briefing contém resumo estruturado com contexto de emails, OneNote, OneDrive "
        "e memórias relevantes aos participantes. Use antes de reuniões para preparar o "
        "usuário. Exemplo: 'recuperar briefing do evento AAMkAGQ3...' passando o ID do "
        "evento no formato Microsoft Graph."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "ID do evento no Outlook (formato Microsoft Graph)",
            },
        },
        "required": ["event_id"],
    },
)


# ---------------------------------------------------------------------------
# Handlers das ferramentas MCP
# ---------------------------------------------------------------------------


async def handle_get_calendar_events(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Busca eventos do calendário no intervalo [start, end]."""
    start = arguments["start"]
    end = arguments["end"]
    params = {
        "$filter": (
            f"start/dateTime ge '{start}T00:00:00Z' "
            f"and end/dateTime le '{end}T23:59:59Z'"
        ),
        "$orderby": "start/dateTime",
        "$select": "subject,start,end,location,organizer,attendees",
        "$top": "50",
    }
    return await graph.fetch_with_params(user, "/me/events", params, db, redis)


async def handle_search_emails(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Busca emails por texto livre."""
    query = arguments["query"]
    limit = min(int(arguments.get("limit", 10)), 50)
    params = {
        "$search": f'"{query}"',
        "$top": str(limit),
        "$select": "subject,from,receivedDateTime,bodyPreview,isRead",
    }
    return await graph.fetch_with_params(user, "/me/messages", params, db, redis)


async def handle_get_onenote_pages(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Lista páginas do OneNote, opcionalmente filtrando por título."""
    query = arguments.get("query")
    params: dict[str, str] = {
        "$top": "50",
        "$select": "title,createdDateTime,lastModifiedDateTime,parentNotebook",
    }
    if query:
        params["$filter"] = f"contains(title, '{query}')"
    return await graph.fetch_with_params(user, "/me/onenote/pages", params, db, redis)


async def handle_search_files(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Busca arquivos no OneDrive por nome ou conteúdo."""
    query = arguments["query"]
    params = {
        "$top": "25",
        "$select": "name,size,lastModifiedDateTime,webUrl,file,folder",
    }
    return await graph.fetch_with_params(
        user, f"/me/drive/root/search(q='{query}')", params, db, redis
    )


async def handle_web_search(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> list[dict]:
    """Busca na web via SearXNG."""
    from app.services.searxng import SearxNGUnavailable

    query = arguments["query"]
    try:
        return await searxng.search(query)
    except SearxNGUnavailable:
        return [
            {
                "error": "web_search indisponível",
                "message": "Esta funcionalidade requer SearXNG self-hosted. "
                "Não está disponível na demo pública.",
            }
        ]


async def handle_semantic_search(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> list[dict]:
    """Busca semântica em todos os serviços do Microsoft 365."""
    from app.services.embeddings import semantic_search as _semantic_search

    query = arguments["query"]
    services = arguments.get("services")
    limit = min(int(arguments.get("limit", 10)), 20)
    return await _semantic_search(db, user.id, query, limit, services)


async def handle_save_memory(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Salva uma memória persistente para sessões futuras."""
    from app.services.memory import save_memory

    content = arguments["content"]
    tags = arguments.get("tags")
    try:
        return await save_memory(db, user.id, content, tags, source="mcp")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def handle_recall_memory(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> list[dict]:
    """Recupera memórias relevantes via busca semântica."""
    from app.services.memory import recall_memory

    query = arguments["query"]
    tags = arguments.get("tags")
    limit = min(int(arguments.get("limit", 5)), 20)
    return await recall_memory(db, user.id, query, tags, limit)


async def handle_get_briefing(
    arguments: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Recupera briefing automático por (user_id, event_id). 404 se não encontrado."""
    event_id = arguments["event_id"]
    stmt = select(Briefing).where(
        Briefing.user_id == user.id,
        Briefing.event_id == event_id,
    )
    result = await db.execute(stmt)
    briefing = result.scalar_one_or_none()
    if briefing is None:
        raise HTTPException(status_code=404, detail="Briefing não encontrado")
    return {
        "id": str(briefing.id),
        "event_id": briefing.event_id,
        "event_subject": briefing.event_subject,
        "event_start": briefing.event_start.isoformat(),
        "event_end": briefing.event_end.isoformat(),
        "attendees": briefing.attendees,
        "content": briefing.content,
        "generated_at": briefing.generated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Registros de ferramentas
# ---------------------------------------------------------------------------

TOOLS_REGISTRY: dict[str, Any] = {
    "get_calendar_events": handle_get_calendar_events,
    "search_emails": handle_search_emails,
    "get_onenote_pages": handle_get_onenote_pages,
    "search_files": handle_search_files,
    "web_search": handle_web_search,
    "semantic_search": handle_semantic_search,
    "save_memory": handle_save_memory,
    "recall_memory": handle_recall_memory,
    "get_briefing": handle_get_briefing,
}

TOOLS_MAP: dict[str, MCPTool] = {
    "get_calendar_events": TOOL_GET_CALENDAR_EVENTS,
    "search_emails": TOOL_SEARCH_EMAILS,
    "get_onenote_pages": TOOL_GET_ONENOTE_PAGES,
    "search_files": TOOL_SEARCH_FILES,
    "web_search": TOOL_WEB_SEARCH,
    "semantic_search": TOOL_SEMANTIC_SEARCH,
    "save_memory": TOOL_SAVE_MEMORY,
    "recall_memory": TOOL_RECALL_MEMORY,
    "get_briefing": TOOL_GET_BRIEFING,
}

ALL_TOOLS: list[MCPTool] = [
    TOOL_GET_CALENDAR_EVENTS,
    TOOL_SEARCH_EMAILS,
    TOOL_GET_ONENOTE_PAGES,
    TOOL_SEARCH_FILES,
    TOOL_WEB_SEARCH,
    TOOL_SEMANTIC_SEARCH,
    TOOL_SAVE_MEMORY,
    TOOL_RECALL_MEMORY,
    TOOL_GET_BRIEFING,
]


# ---------------------------------------------------------------------------
# Funções auxiliares — audit (Fase 7)
# ---------------------------------------------------------------------------


def _summarize_arguments(arguments: dict) -> dict:
    """Resumo seguro de argumentos — chaves + tamanhos, sem PII.

    Não loga conteúdo de query, content de memória, etc.
    string  → {"type": "string", "length": int}
    array   → {"type": "array", "length": int}
    int/float/bool → {"type": "<typename>", "value": <value>}
    None    → {"type": "null"}
    other   → {"type": "<typename>"}
    """
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            summary[key] = {"type": "string", "length": len(value)}
        elif isinstance(value, list):
            summary[key] = {"type": "array", "length": len(value)}
        elif isinstance(value, (int, float, bool)):
            summary[key] = {"type": type(value).__name__, "value": value}
        elif value is None:
            summary[key] = {"type": "null"}
        else:
            summary[key] = {"type": type(value).__name__}
    return summary


# ---------------------------------------------------------------------------
# Funções auxiliares JSON-RPC 2.0
# ---------------------------------------------------------------------------


def jsonrpc_success(request_id: str | int | None, data: Any) -> dict:
    """Resposta JSON-RPC 2.0 de sucesso com dados serializados."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {"type": "text", "text": json.dumps(data, default=str, ensure_ascii=False)}
            ],
            "isError": False,
        },
    }


def jsonrpc_error(request_id: str | int | None, code: int, message: str) -> dict:
    """Resposta JSON-RPC 2.0 de erro de protocolo."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def jsonrpc_domain_error(request_id: str | int | None, message: str) -> dict:
    """Resposta JSON-RPC 2.0 de erro de domínio (isError=true no result)."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": f"Erro: {message}"}],
            "isError": True,
        },
    }


# ---------------------------------------------------------------------------
# Dependencies (async generators)
# ---------------------------------------------------------------------------


async def get_graph_service() -> AsyncGenerator[GraphService, None]:
    """Cria e fecha uma instância de GraphService."""
    service = GraphService()
    try:
        yield service
    finally:
        await service.close()


async def get_searxng_service() -> AsyncGenerator[SearXNGService, None]:
    """Cria e fecha uma instância de SearXNGService."""
    service = SearXNGService()
    try:
        yield service
    finally:
        await service.close()


# ---------------------------------------------------------------------------
# Handler interno: _handle_initialize (Fase 11 — handshake MCP)
# ---------------------------------------------------------------------------


def _handle_initialize(request_id: str | int | None, params: dict) -> dict:
    """Retorna protocolVersion, capabilities e serverInfo."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    }


# ---------------------------------------------------------------------------
# Handler interno: _handle_tools_list (Fase 11 — lista de tools)
# ---------------------------------------------------------------------------


def _handle_tools_list(request_id: str | int | None) -> dict:
    """Retorna lista de tools com name, description, inputSchema."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [tool.model_dump() for tool in ALL_TOOLS],
        },
    }


# ---------------------------------------------------------------------------
# Handler interno: _handle_ping (Fase 11 — responde ping com result vazio)
# ---------------------------------------------------------------------------


def _handle_ping(request_id: str | int | None) -> dict:
    """Retorna result vazio ({})."""
    return {"jsonrpc": "2.0", "id": request_id, "result": {}}


# ---------------------------------------------------------------------------
# Handler interno: _handle_tools_call (Fase 11 — reuso entre endpoints)
# ---------------------------------------------------------------------------


async def _handle_tools_call(
    request_id: str | int | None,
    params: dict,
    user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
    graph: GraphService,
    searxng: SearXNGService,
) -> dict:
    """Executa tools/call: valida tool, valida params, dispatcha, audita.

    Retorna dict JSON-RPC completo (sucesso, erro de protocolo ou erro de domínio).
    Audit log só é registrado quando a tool passa validação de nome e params.
    """
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    # Validar tool existe — NÃO gera audit log
    if tool_name not in TOOLS_REGISTRY:
        return jsonrpc_error(request_id, -32601, f"Ferramenta '{tool_name}' não encontrada")

    # Validar params obrigatórios — NÃO gera audit log
    tool_def = TOOLS_MAP[tool_name]
    required_params = tool_def.inputSchema.get("required", [])
    for param in required_params:
        if param not in arguments:
            return jsonrpc_error(
                request_id,
                -32602,
                f"Parâmetro obrigatório ausente: '{param}' na ferramenta '{tool_name}'",
            )

    # Dispatch + medição — a partir daqui, audit log SEMPRE é registrado
    started_at = time.monotonic()
    success = True
    error_msg: str | None = None
    try:
        handler = TOOLS_REGISTRY[tool_name]
        data = await handler(arguments, user, db, redis, graph, searxng)
        response = jsonrpc_success(request_id, data)
    except HTTPException as exc:
        success = False
        error_msg = str(exc.detail)
        response = jsonrpc_domain_error(request_id, str(exc.detail))
    except Exception as exc:
        success = False
        error_msg = f"Erro interno: {exc}"
        logger.exception("Erro interno na ferramenta %s", tool_name)
        response = jsonrpc_domain_error(request_id, error_msg)

    elapsed_ms = int((time.monotonic() - started_at) * 1000)

    # Audit log
    await log_event(
        db,
        user_id=user.id,
        event_type=AuditEventType.MCP_CALL,
        event_data={
            "tool_name": tool_name,
            "arguments_summary": _summarize_arguments(arguments),
            "success": success,
            "error_message": error_msg,
        },
        success=success,
        error_message=error_msg,
        latency_ms=elapsed_ms,
    )

    return response


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_tools(user: User = Depends(get_current_user)) -> dict:
    """Lista todas as ferramentas MCP disponíveis (JSON-RPC 2.0)."""
    return {
        "jsonrpc": "2.0",
        "result": {
            "tools": [tool.model_dump() for tool in ALL_TOOLS],
        },
    }


@router.post("")
@router.post("/")
async def mcp_dispatch(
    request: MCPCallRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph: GraphService = Depends(get_graph_service),
    searxng: SearXNGService = Depends(get_searxng_service),
) -> Response:
    """Dispatcher JSON-RPC 2.0 conforme MCP spec 2025-06-18 (Streamable HTTP)."""
    # Validar envelope
    if request.jsonrpc != "2.0":
        return JSONResponse(jsonrpc_error(request.id, -32600, "jsonrpc deve ser '2.0'"))

    method = request.method
    params = request.params

    # Notification: notifications/initialized → 202 sem body (política permissiva: ignora id)
    if method == "notifications/initialized":
        return Response(status_code=202)

    # Dispatch por método
    if method == "initialize":
        response_data = _handle_initialize(request.id, params)
    elif method == "ping":
        response_data = _handle_ping(request.id)
    elif method == "tools/list":
        response_data = _handle_tools_list(request.id)
    elif method == "tools/call":
        response_data = await _handle_tools_call(
            request.id, params, user, db, redis, graph, searxng
        )
    else:
        response_data = jsonrpc_error(request.id, -32601, f"Método '{method}' não suportado")

    # Header de sessão stateless
    headers = {}
    if method == "initialize":
        headers["Mcp-Session-Id"] = str(uuid.uuid4())

    return JSONResponse(response_data, headers=headers)


@router.post("/call")
async def call_tool(
    request: MCPCallRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph: GraphService = Depends(get_graph_service),
    searxng: SearXNGService = Depends(get_searxng_service),
) -> JSONResponse:
    """Executa uma ferramenta MCP via JSON-RPC 2.0 (endpoint legado — deprecated)."""
    logger.warning("deprecated endpoint POST /mcp/call usado — cliente deve migrar para POST /mcp")

    # Validação de protocolo — method (apenas tools/call permitido neste endpoint)
    if request.method != "tools/call":
        return JSONResponse(
            jsonrpc_error(request.id, -32601, f"Método '{request.method}' não suportado")
        )

    # Delegar para handler compartilhado
    result = await _handle_tools_call(
        request.id, request.params, user, db, redis, graph, searxng
    )
    return JSONResponse(result)


@router.get("/sse")
async def mcp_sse(
    request: Request,
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Conexão SSE keepalive para clientes MCP."""

    async def event_generator():
        # Evento hello com capabilities
        yield f"data: {json.dumps({'type': 'hello', 'capabilities': {'tools': {}}})}\n\n"

        # Pings a cada 30 segundos até desconexão
        try:
            while True:
                await asyncio.sleep(30)
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
