"""Serviço de cache Redis com TTLs diferenciados por serviço.

Gerencia operações de cache (get, set, invalidate) para dados da
Microsoft Graph API, usando chaves no formato ``lanez:{user_id}:{service}``
e TTLs específicos por tipo de serviço.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.schemas.graph import ServiceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeamento de TTL por serviço (em segundos)
# ---------------------------------------------------------------------------

TTL_MAP: dict[ServiceType, int] = {
    ServiceType.CALENDAR: 300,   # 5 minutos
    ServiceType.MAIL: 300,       # 5 minutos
    ServiceType.ONENOTE: 900,    # 15 minutos
    ServiceType.ONEDRIVE: 900,   # 15 minutos
}


def cache_key(user_id: str, service: str) -> str:
    """Retorna a chave de cache no formato ``lanez:{user_id}:{service}``."""
    return f"lanez:{user_id}:{service}"


def get_ttl(service: ServiceType) -> int:
    """Retorna o TTL em segundos para o serviço informado."""
    return TTL_MAP[service]


class CacheService:
    """Operações de cache Redis para dados da Graph API."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def get(self, user_id: str, service: ServiceType) -> Any | None:
        """Busca dados do cache. Retorna ``None`` se não houver hit."""
        key = cache_key(user_id, service.value)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Cache corrompido para chave %s — ignorando", key)
            return None

    async def set(
        self, user_id: str, service: ServiceType, data: Any
    ) -> None:
        """Armazena dados no cache com o TTL correspondente ao serviço."""
        key = cache_key(user_id, service.value)
        ttl = get_ttl(service)
        await self._redis.set(key, json.dumps(data), ex=ttl)

    async def invalidate(self, user_id: str, service: ServiceType) -> None:
        """Remove a entrada de cache para um usuário/serviço específico."""
        key = cache_key(user_id, service.value)
        await self._redis.delete(key)

    async def invalidate_all(self, user_id: str) -> None:
        """Remove todas as entradas de cache de um usuário (4 serviços)."""
        keys = [cache_key(user_id, svc.value) for svc in ServiceType]
        if keys:
            await self._redis.delete(*keys)
