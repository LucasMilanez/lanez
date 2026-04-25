"""Serviço de integração com o SearXNG (busca web self-hosted).

Encapsula o cliente HTTP com timeout de 10s e tratamento gracioso de erros.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0  # segundos


class SearXNGService:
    """Cliente HTTP para o motor de busca SearXNG."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT)

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        await self._client.aclose()

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Consulta o SearXNG e retorna até *limit* resultados.

        Retorna lista de ``{title, url, content}``.
        Em caso de erro HTTP ou timeout, retorna lista vazia e loga o erro.
        """
        params = {"q": query, "format": "json"}
        try:
            resp = await self._client.get(
                f"{settings.SEARXNG_URL}/search", params=params
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])[:limit]
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in results
            ]
        except httpx.HTTPError as exc:
            logger.error("Erro SearXNG: %s", exc)
            return []
