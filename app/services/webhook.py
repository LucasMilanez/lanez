"""Serviço de gerenciamento de webhooks da Microsoft Graph API.

Encapsula a criação de subscrições de webhook para os 4 serviços
(calendar, mail, onenote, onedrive), persistindo os dados no banco.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.schemas.graph import ServiceType, WebhookNotification
from app.services.cache import CacheService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://graph.microsoft.com/v1.0"

SUBSCRIPTION_RESOURCES: dict[ServiceType, str] = {
    ServiceType.CALENDAR: "/me/events",
    ServiceType.MAIL: "/me/messages",
    ServiceType.ONENOTE: "/me/onenote/pages",
    ServiceType.ONEDRIVE: "/me/drive/root",
}

RESOURCE_TO_SERVICE: dict[str, ServiceType] = {
    resource: service for service, resource in SUBSCRIPTION_RESOURCES.items()
}

_TIMEOUT = 30.0  # segundos
_EXPIRATION_MINUTES = 4230  # tempo máximo de subscrição Graph API


class WebhookService:
    """Gerencia subscrições de webhook da Microsoft Graph API.

    Mantém um ``httpx.AsyncClient`` compartilhado com timeout de 30 s,
    seguindo o mesmo padrão do ``GraphService``.
    """

    BASE_URL: str = BASE_URL
    SUBSCRIPTION_RESOURCES: dict[ServiceType, str] = SUBSCRIPTION_RESOURCES

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
    # Criação de subscrições
    # ------------------------------------------------------------------

    async def create_subscriptions(
        self,
        user_id: uuid.UUID,
        access_token: str,
        db: AsyncSession,
    ) -> list[WebhookSubscription]:
        """Cria subscrições de webhook para os 4 serviços na Graph API.

        Para cada serviço (calendar, mail, onenote, onedrive):
        1. POST para /subscriptions com changeType, notificationUrl,
           resource, expirationDateTime e clientState
        2. Persiste o ``WebhookSubscription`` no banco

        Args:
            user_id: UUID do usuário autenticado.
            access_token: Token de acesso válido para a Graph API.
            db: Sessão assíncrona do SQLAlchemy.

        Returns:
            Lista de ``WebhookSubscription`` criadas com sucesso.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/subscriptions"
        notification_url = settings.WEBHOOK_NOTIFICATION_URL
        expiration = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRATION_MINUTES)
        expiration_str = expiration.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

        created: list[WebhookSubscription] = []

        for service_type, resource in self.SUBSCRIPTION_RESOURCES.items():
            body = {
                "changeType": "created,updated,deleted",
                "notificationUrl": notification_url,
                "resource": resource,
                "expirationDateTime": expiration_str,
                "clientState": settings.WEBHOOK_CLIENT_STATE,
            }

            try:
                resp = await self._client.post(url, json=body, headers=headers)

                if resp.status_code not in (200, 201):
                    logger.error(
                        "Falha ao criar subscrição %s para user_id=%s — status=%d body=%s [token=REDACTED]",
                        service_type.value,
                        user_id,
                        resp.status_code,
                        resp.text,
                    )
                    continue

                data = resp.json()
                subscription = WebhookSubscription(
                    user_id=user_id,
                    subscription_id=data["id"],
                    resource=resource,
                    client_state=settings.WEBHOOK_CLIENT_STATE,
                    expires_at=expiration,
                )
                db.add(subscription)
                created.append(subscription)

                logger.info(
                    "Subscrição criada: service=%s subscription_id=%s user_id=%s [token=REDACTED]",
                    service_type.value,
                    data["id"],
                    user_id,
                )

            except httpx.HTTPError as exc:
                logger.error(
                    "Erro HTTP ao criar subscrição %s para user_id=%s — %s [token=REDACTED]",
                    service_type.value,
                    user_id,
                    exc,
                )
                continue

        if created:
            await db.commit()
            logger.info(
                "Total de %d subscrições criadas para user_id=%s [token=REDACTED]",
                len(created),
                user_id,
            )

        return created

    # ------------------------------------------------------------------
    # Renovação de subscrições
    # ------------------------------------------------------------------

    async def renew_subscriptions(self, db: AsyncSession) -> None:
        """Renova subscrições de webhook próximas de expirar.

        Consulta subscrições com ``expires_at < now + 60 minutos`` e tenta
        renová-las via PATCH na Graph API. Se o PATCH falhar, deleta a
        subscrição antiga e cria uma nova via POST.

        Este método é projetado para rodar em um loop de background e
        nunca propaga exceções — erros são logados e o processamento
        continua para as demais subscrições.

        Args:
            db: Sessão assíncrona do SQLAlchemy.
        """
        try:
            threshold = datetime.now(timezone.utc) + timedelta(minutes=60)
            stmt = select(WebhookSubscription).where(
                WebhookSubscription.expires_at < threshold
            )
            result = await db.execute(stmt)
            expiring = result.scalars().all()

            if not expiring:
                return

            logger.info(
                "Encontradas %d subscrições para renovar [token=REDACTED]",
                len(expiring),
            )

            for subscription in expiring:
                await self._renew_single(subscription, db)

            await db.commit()

        except Exception:
            logger.exception(
                "Erro inesperado no loop de renovação de subscrições [token=REDACTED]"
            )

    async def _renew_single(
        self,
        subscription: WebhookSubscription,
        db: AsyncSession,
    ) -> None:
        """Tenta renovar uma única subscrição via PATCH; recria se falhar."""
        # Buscar o access_token do usuário dono da subscrição
        user = await db.get(User, subscription.user_id)
        if user is None:
            logger.warning(
                "Usuário não encontrado para subscrição subscription_id=%s user_id=%s — removendo subscrição [token=REDACTED]",
                subscription.subscription_id,
                subscription.user_id,
            )
            await db.delete(subscription)
            return

        try:
            access_token = user.microsoft_access_token
        except Exception:
            logger.exception(
                "Falha ao descriptografar token para user_id=%s — ignorando renovação [token=REDACTED]",
                subscription.user_id,
            )
            return

        new_expiration = datetime.now(timezone.utc) + timedelta(
            minutes=_EXPIRATION_MINUTES
        )
        new_expiration_str = new_expiration.strftime(
            "%Y-%m-%dT%H:%M:%S.0000000Z"
        )

        headers = {"Authorization": f"Bearer {access_token}"}
        patch_url = f"{self.BASE_URL}/subscriptions/{subscription.subscription_id}"

        try:
            resp = await self._client.patch(
                patch_url,
                json={"expirationDateTime": new_expiration_str},
                headers=headers,
            )

            if resp.status_code in (200, 201):
                subscription.expires_at = new_expiration
                logger.info(
                    "Subscrição renovada: subscription_id=%s user_id=%s [token=REDACTED]",
                    subscription.subscription_id,
                    subscription.user_id,
                )
                return

            # PATCH falhou — logar e recriar
            logger.error(
                "Falha ao renovar subscrição subscription_id=%s — status=%d body=%s [token=REDACTED]",
                subscription.subscription_id,
                resp.status_code,
                resp.text,
            )

        except httpx.HTTPError as exc:
            logger.error(
                "Erro HTTP ao renovar subscrição subscription_id=%s — %s [token=REDACTED]",
                subscription.subscription_id,
                exc,
            )

        # Falha no PATCH: deletar a subscrição antiga e criar nova
        resource = subscription.resource
        user_id = subscription.user_id
        await db.delete(subscription)

        # Recriar subscrição para o mesmo recurso
        await self._recreate_subscription(user_id, access_token, resource, db)

    async def _recreate_subscription(
        self,
        user_id: uuid.UUID,
        access_token: str,
        resource: str,
        db: AsyncSession,
    ) -> None:
        """Cria uma nova subscrição para um recurso específico via POST."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self.BASE_URL}/subscriptions"
        notification_url = settings.WEBHOOK_NOTIFICATION_URL
        expiration = datetime.now(timezone.utc) + timedelta(
            minutes=_EXPIRATION_MINUTES
        )
        expiration_str = expiration.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

        body = {
            "changeType": "created,updated,deleted",
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration_str,
            "clientState": settings.WEBHOOK_CLIENT_STATE,
        }

        try:
            resp = await self._client.post(url, json=body, headers=headers)

            if resp.status_code not in (200, 201):
                logger.error(
                    "Falha ao recriar subscrição resource=%s user_id=%s — status=%d body=%s [token=REDACTED]",
                    resource,
                    user_id,
                    resp.status_code,
                    resp.text,
                )
                return

            data = resp.json()
            new_sub = WebhookSubscription(
                user_id=user_id,
                subscription_id=data["id"],
                resource=resource,
                client_state=settings.WEBHOOK_CLIENT_STATE,
                expires_at=expiration,
            )
            db.add(new_sub)

            logger.info(
                "Subscrição recriada: resource=%s subscription_id=%s user_id=%s [token=REDACTED]",
                resource,
                data["id"],
                user_id,
            )

        except httpx.HTTPError as exc:
            logger.error(
                "Erro HTTP ao recriar subscrição resource=%s user_id=%s — %s [token=REDACTED]",
                resource,
                user_id,
                exc,
            )

    # ------------------------------------------------------------------
    # Processamento de notificações
    # ------------------------------------------------------------------

    async def process_notification(
        self,
        notification: WebhookNotification,
        cache_service: CacheService,
        db: AsyncSession,
    ) -> tuple[uuid.UUID, ServiceType, str | None] | None:
        """Processa uma notificação de webhook da Microsoft Graph.

        Fluxo:
        1. Valida ``clientState`` contra ``WEBHOOK_CLIENT_STATE``
        2. Busca a subscrição no banco pelo ``subscription_id``
        3. Mapeia o ``resource`` para ``ServiceType`` e extrai ``user_id``
        4. Invalida o cache via ``CacheService.invalidate()``
        5. Extrai ``event_id`` do resource para notificações CALENDAR

        Args:
            notification: Dados da notificação recebida.
            cache_service: Instância do serviço de cache Redis.
            db: Sessão assíncrona do SQLAlchemy.

        Returns:
            Tupla ``(user_id, service_type, event_id)`` se a notificação foi
            processada com sucesso, ou ``None`` se a subscrição não foi
            encontrada ou o resource não pôde ser mapeado. ``event_id`` é
            ``str`` para notificações CALENDAR, ``None`` para outros serviços.

        Raises:
            HTTPException: 403 se ``clientState`` não corresponder ao esperado.
        """
        # 1. Validar clientState
        if notification.client_state != settings.WEBHOOK_CLIENT_STATE:
            logger.warning(
                "clientState inválido para subscription_id=%s — rejeitando notificação [clientState=REDACTED]",
                notification.subscription_id,
            )
            raise HTTPException(status_code=403, detail="clientState inválido")

        # 2. Buscar subscrição no banco pelo subscription_id
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.subscription_id == notification.subscription_id
        )
        result = await db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if subscription is None:
            logger.warning(
                "Subscrição não encontrada: subscription_id=%s",
                notification.subscription_id,
            )
            return None

        # 3. Mapear resource para ServiceType
        user_id = subscription.user_id
        resource = subscription.resource
        service_type = RESOURCE_TO_SERVICE.get(resource)

        if service_type is None:
            logger.warning(
                "Resource desconhecido: resource=%s subscription_id=%s user_id=%s",
                resource,
                notification.subscription_id,
                user_id,
            )
            return None

        # 4. Invalidar cache
        await cache_service.invalidate(str(user_id), service_type)
        logger.info(
            "Cache invalidado: service=%s user_id=%s subscription_id=%s",
            service_type.value,
            user_id,
            notification.subscription_id,
        )

        # 5. Extrair event_id para notificações CALENDAR
        event_id: str | None = None
        if service_type == ServiceType.CALENDAR:
            parts = notification.resource.split("/Events/")
            event_id = parts[1] if len(parts) == 2 else None

        return user_id, service_type, event_id
