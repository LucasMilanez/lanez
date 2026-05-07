"""Serviço de integração com a Microsoft Graph API.

Encapsula o cliente HTTP, mapeamento de endpoints por serviço,
rate limiting, exponential backoff e lógica de cache.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.cache import GraphCache
from app.models.user import User
from app.schemas.graph import GraphDataResponse, ServiceType
from app.services.cache import CacheService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://graph.microsoft.com/v1.0"

ENDPOINTS: dict[ServiceType, str] = {
    ServiceType.CALENDAR: "/me/events",
    ServiceType.MAIL: "/me/messages",
    ServiceType.ONENOTE: "/me/onenote/pages",
    ServiceType.ONEDRIVE: "/me/drive/root/children",
}

_TIMEOUT = 30.0  # segundos

# Rate limiting
_RATE_LIMIT_WINDOW = 900  # 15 minutos em segundos
_RATE_LIMIT_MAX = 200  # requisições por janela

# Exponential backoff
_BACKOFF_MAX_RETRIES = 3

# Leitura de conteúdo de ficheiros
_FILE_CONTENT_MAX_BYTES = 100 * 1024  # 100 KB
_READABLE_EXTENSIONS = {".txt", ".md", ".csv", ".docx"}


def calculate_backoff(attempt: int) -> int:
    """Retorna o tempo de espera em segundos para a tentativa *attempt* (1-based).

    Fórmula: 2^(attempt - 1) → 1s, 2s, 4s …
    """
    return 2 ** (attempt - 1)

# Token refresh
_TOKEN_URL_TEMPLATE = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
)


class GraphService:
    """Cliente para a Microsoft Graph API v1.0.

    Mantém um ``httpx.AsyncClient`` compartilhado com timeout de 30 s.
    """

    BASE_URL: str = BASE_URL
    ENDPOINTS: dict[ServiceType, str] = ENDPOINTS

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)

    @property
    def client(self) -> httpx.AsyncClient:
        """Retorna o ``httpx.AsyncClient`` subjacente."""
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _check_rate_limit(
        self, redis: aioredis.Redis, user_id: uuid.UUID
    ) -> None:
        """Incrementa o contador de rate limit e levanta HTTP 429 se excedido."""
        key = f"lanez:ratelimit:{user_id}"
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, _RATE_LIMIT_WINDOW)
        if current > _RATE_LIMIT_MAX:
            ttl = await redis.ttl(key)
            logger.warning(
                "Rate limit excedido para user_id=%s — %d/%d (reset em %ds)",
                user_id,
                current,
                _RATE_LIMIT_MAX,
                ttl,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit excedido. Tente novamente mais tarde.",
            )

    # --------------------------------------------------------Le----------
    # Token refresh
    # ------------------------------------------------------------------

    async def _refresh_access_token(
        self, user: User, db: AsyncSession
    ) -> str:
        """Renova o access_token via Entra ID e persiste os novos tokens."""
        token_url = _TOKEN_URL_TEMPLATE.format(
            tenant_id=settings.MICROSOFT_TENANT_ID
        )
        payload = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": user.microsoft_refresh_token,
        }
        resp = await self._client.post(token_url, data=payload)
        if resp.status_code != 200:
            logger.error(
                "Falha ao renovar token para user_id=%s — status=%d",
                user.id,
                resp.status_code,
            )
            raise HTTPException(
                status_code=401,
                detail="Não foi possível renovar o token. Re-autenticação necessária.",
            )

        data = resp.json()
        user.microsoft_access_token = data["access_token"]
        user.microsoft_refresh_token = data["refresh_token"]
        user.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=data.get("expires_in", 3600)
        )
        await db.commit()
        logger.info(
            "Token renovado com sucesso para user_id=%s [token=REDACTED]",
            user.id,
        )
        return data["access_token"]

    # ------------------------------------------------------------------
    # Graph API request with 429 backoff
    # ------------------------------------------------------------------

    async def _request_graph(
        self, url: str, access_token: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        """Faz GET na Graph API com exponential backoff para HTTP 429."""
        headers = {"Authorization": f"Bearer {access_token}"}

        for attempt in range(1, _BACKOFF_MAX_RETRIES + 1):
            resp = await self._client.get(url, headers=headers, params=params)

            if resp.status_code != 429:
                return resp

            # Ler Retry-After ou aplicar backoff exponencial
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                wait = int(retry_after)
            else:
                wait = calculate_backoff(attempt)  # 1s, 2s, 4s

            logger.warning(
                "Graph API 429 (tentativa %d/%d) — aguardando %ds [token=REDACTED]",
                attempt,
                _BACKOFF_MAX_RETRIES,
                wait,
            )
            await asyncio.sleep(wait)

        # Todas as tentativas esgotadas — propagar 429
        logger.error(
            "Graph API 429 persistente após %d tentativas [token=REDACTED]",
            _BACKOFF_MAX_RETRIES,
        )
        raise HTTPException(
            status_code=429,
            detail="Microsoft Graph API indisponível (rate limited). Tente mais tarde.",
        )

    # ------------------------------------------------------------------
    # Graph API POST request with 429 backoff
    # ------------------------------------------------------------------

    async def _post_graph(
        self, url: str, access_token: str, body: dict
    ) -> httpx.Response:
        """Faz POST na Graph API com exponential backoff para HTTP 429."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, _BACKOFF_MAX_RETRIES + 1):
            resp = await self._client.post(url, headers=headers, json=body)

            if resp.status_code != 429:
                return resp

            retry_after = resp.headers.get("Retry-After")
            wait = int(retry_after) if retry_after is not None else calculate_backoff(attempt)
            logger.warning(
                "Graph API POST 429 (tentativa %d/%d) — aguardando %ds",
                attempt, _BACKOFF_MAX_RETRIES, wait,
            )
            await asyncio.sleep(wait)

        logger.error(
            "Graph API POST 429 persistente após %d tentativas",
            _BACKOFF_MAX_RETRIES,
        )
        raise HTTPException(
            status_code=429,
            detail="Microsoft Graph API indisponível (rate limited). Tente mais tarde.",
        )

    # ------------------------------------------------------------------
    # Persistência no GraphCache (upsert)
    # ------------------------------------------------------------------

    async def _persist_graph_cache(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        service: ServiceType,
        data: dict | list,
        ttl_seconds: int,
    ) -> None:
        """Upsert no GraphCache por (user_id, service, resource_id)."""
        now = datetime.now(timezone.utc)
        resource_id = service.value  # recurso padrão por serviço

        stmt = select(GraphCache).where(
            GraphCache.user_id == user_id,
            GraphCache.service == service.value,
            GraphCache.resource_id == resource_id,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.data = data
            existing.cached_at = now
            existing.expires_at = now + timedelta(seconds=ttl_seconds)
        else:
            entry = GraphCache(
                user_id=user_id,
                service=service.value,
                resource_id=resource_id,
                data=data if isinstance(data, dict) else {"items": data},
                cached_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            db.add(entry)

        await db.commit()

    # ------------------------------------------------------------------
    # fetch_with_params — consulta parametrizada sem cache
    # ------------------------------------------------------------------

    async def fetch_with_params(
        self,
        user: User,
        endpoint: str,
        params: dict[str, str],
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> dict:
        """Consulta a Graph API com parâmetros customizados, sem cache.

        Fluxo:
        1. Verificar rate limit por usuário
        2. GET Graph API com Bearer token e params
        3. Tratar 401 (renovar token + retry 1×)
        4. Propagar outros erros como HTTPException
        5. Retornar resp.json()

        NÃO usa cache Redis nem GraphCache.
        """
        # 1. Verificar rate limit
        await self._check_rate_limit(redis, user.id)

        # 2. Montar URL e obter token
        url = f"{self.BASE_URL}{endpoint}"
        access_token = user.microsoft_access_token

        # 3. Requisição com backoff para 429
        resp = await self._request_graph(url, access_token, params=params)

        # 4. Tratar 401 — refresh + retry 1×
        if resp.status_code == 401:
            logger.info(
                "Graph API 401 para user_id=%s endpoint=%s — renovando token [token=REDACTED]",
                user.id,
                endpoint,
            )
            new_token = await self._refresh_access_token(user, db)
            resp = await self._request_graph(url, new_token, params=params)
            if resp.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Token inválido. Re-autentique.",
                )

        # 5. Propagar outros erros
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Erro Graph API: {resp.status_code}",
            )

        return resp.json()

    # ------------------------------------------------------------------
    # post_graph_search — pesquisa via Graph Search API
    # ------------------------------------------------------------------

    async def post_graph_search(
        self,
        user: User,
        entity_types: list[str],
        query_string: str,
        fields: list[str],
        limit: int,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> list[dict]:
        """Pesquisa via Graph Search API (POST /search/query).

        Suporta OneDrive pessoal e SharePoint simultaneamente.
        Retorna lista de hits com os campos pedidos.
        """
        await self._check_rate_limit(redis, user.id)

        url = f"{self.BASE_URL}/search/query"
        body = {
            "requests": [{
                "entityTypes": entity_types,
                "query": {"queryString": query_string},
                "from": 0,
                "size": limit,
                "fields": fields,
            }]
        }
        access_token = user.microsoft_access_token
        resp = await self._post_graph(url, access_token, body)

        if resp.status_code == 401:
            logger.info("Graph Search 401 para user_id=%s — renovando token", user.id)
            new_token = await self._refresh_access_token(user, db)
            resp = await self._post_graph(url, new_token, body)
            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Token inválido. Re-autentique.")

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Erro Graph Search API: {resp.status_code}",
            )

        data = resp.json()
        hits: list[dict] = []
        for response in data.get("value", []):
            for hit_container in response.get("hitsContainers", []):
                hits.extend(hit_container.get("hits", []))
        return hits

    # ------------------------------------------------------------------
    # read_drive_item_content — download de conteúdo de ficheiro
    # ------------------------------------------------------------------

    async def read_drive_item_content(
        self,
        user: User,
        drive_id: str,
        item_id: str,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> bytes | None:
        """Faz GET /drives/{driveId}/items/{itemId}/content — retorna bytes raw.

        Retorna None se o ficheiro for maior que _FILE_CONTENT_MAX_BYTES.
        Segue o redirect que a Graph API emite (follow_redirects=True).
        """
        await self._check_rate_limit(redis, user.id)

        url = f"{self.BASE_URL}/drives/{drive_id}/items/{item_id}/content"
        access_token = user.microsoft_access_token
        headers = {"Authorization": f"Bearer {access_token}"}

        resp = await self._client.get(url, headers=headers, follow_redirects=True)

        if resp.status_code == 401:
            new_token = await self._refresh_access_token(user, db)
            headers = {"Authorization": f"Bearer {new_token}"}
            resp = await self._client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Token inválido. Re-autentique.")

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Erro ao ler ficheiro: {resp.status_code}",
            )

        if len(resp.content) > _FILE_CONTENT_MAX_BYTES:
            return None  # Chamador interpreta None como "demasiado grande"

        return resp.content

    # ------------------------------------------------------------------
    # read_onenote_page_content — conteúdo HTML de uma página OneNote
    # ------------------------------------------------------------------

    async def read_onenote_page_content(
        self,
        user: User,
        page_id: str,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> str | None:
        """Faz GET /me/onenote/pages/{id}/content — retorna texto sem HTML.

        Retorna None se a página for maior que _FILE_CONTENT_MAX_BYTES ou inacessível.
        """
        import re

        await self._check_rate_limit(redis, user.id)

        url = f"{self.BASE_URL}/me/onenote/pages/{page_id}/content"
        access_token = user.microsoft_access_token

        resp = await self._request_graph(url, access_token)

        if resp.status_code == 401:
            new_token = await self._refresh_access_token(user, db)
            resp = await self._request_graph(url, new_token)
            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Token inválido. Re-autentique.")

        if resp.status_code != 200:
            return None

        if len(resp.content) > _FILE_CONTENT_MAX_BYTES:
            return None

        html = resp.text
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    # ------------------------------------------------------------------
    # resolve_share_url — resolve URL partilhado para driveItem
    # ------------------------------------------------------------------

    async def resolve_share_url(
        self,
        user: User,
        share_url: str,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> dict:
        """Resolve um URL do SharePoint/OneDrive para driveItem via /shares/{encoded}/driveItem.

        O share_id é u!<base64url(url)> conforme a Graph API Sharing spec.
        """
        import base64

        await self._check_rate_limit(redis, user.id)

        encoded = base64.urlsafe_b64encode(share_url.encode()).rstrip(b"=").decode()
        share_id = f"u!{encoded}"
        url = f"{self.BASE_URL}/shares/{share_id}/driveItem"
        access_token = user.microsoft_access_token

        resp = await self._request_graph(url, access_token)

        if resp.status_code == 401:
            new_token = await self._refresh_access_token(user, db)
            resp = await self._request_graph(url, new_token)
            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Token inválido. Re-autentique.")

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Não foi possível resolver o URL partilhado: {resp.status_code}",
            )

        return resp.json()

    # ------------------------------------------------------------------
    # fetch_data — fluxo principal
    # ------------------------------------------------------------------

    async def fetch_data(
        self,
        user_id: uuid.UUID,
        service: ServiceType,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> GraphDataResponse:
        """Consulta dados da Graph API com cache, rate limit e retry.

        Fluxo:
        1. Verificar cache Redis (hit → retorno imediato)
        2. Verificar rate limit por usuário
        3. GET Graph API com Bearer token
        4. Tratar 401 (renovar token + retry 1×)
        5. Tratar 429 (backoff exponencial)
        6. Salvar no cache Redis
        7. Persistir no GraphCache (PostgreSQL)
        8. Retornar GraphDataResponse
        """
        from app.services.cache import CacheService, get_ttl

        cache_svc = CacheService(redis)

        # 1. Verificar cache Redis
        cached = await cache_svc.get(str(user_id), service)
        if cached is not None:
            logger.debug(
                "Cache hit para user_id=%s service=%s", user_id, service.value
            )
            return GraphDataResponse(
                service=service,
                data=cached,
                from_cache=True,
                cached_at=datetime.now(timezone.utc),
            )

        # 2. Verificar rate limit
        await self._check_rate_limit(redis, user_id)

        # 3. Buscar usuário para obter access_token
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        url = f"{self.BASE_URL}{self.ENDPOINTS[service]}"
        access_token = user.microsoft_access_token

        # 3-5. GET Graph API com tratamento de 401 e 429
        resp = await self._request_graph(url, access_token)

        # 4. Tratar 401 — renovar token e retry 1×
        if resp.status_code == 401:
            logger.info(
                "Graph API 401 para user_id=%s service=%s — renovando token [token=REDACTED]",
                user_id,
                service.value,
            )
            new_token = await self._refresh_access_token(user, db)
            resp = await self._request_graph(url, new_token)

            if resp.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Token inválido mesmo após renovação. Re-autenticação necessária.",
                )

        # Propagar outros erros
        if resp.status_code != 200:
            logger.error(
                "Graph API erro %d para user_id=%s service=%s",
                resp.status_code,
                user_id,
                service.value,
            )
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Erro na Graph API: {resp.status_code}",
            )

        response_data = resp.json()

        # 6. Salvar no cache Redis
        await cache_svc.set(str(user_id), service, response_data)

        # 7. Persistir no GraphCache (PostgreSQL)
        ttl = get_ttl(service)
        await self._persist_graph_cache(db, user_id, service, response_data, ttl)

        # 8. Retornar GraphDataResponse
        return GraphDataResponse(
            service=service,
            data=response_data,
            from_cache=False,
            cached_at=datetime.now(timezone.utc),
        )
