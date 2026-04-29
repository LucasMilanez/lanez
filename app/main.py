"""Aplicação principal FastAPI — Lanez Fase 1.

Configura o lifespan (startup/shutdown), registra routers e middleware CORS.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, close_redis, engine, init_redis
from app.models import Base  # importa Base + todos os modelos (side-effect)
from app.routers import auth, briefings, graph, mcp, memories, status, voice, webhooks
from app.services.embeddings import get_model
from app.services.webhook import WebhookService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Loop de renovação de subscrições de webhook
# ---------------------------------------------------------------------------


async def renewal_loop() -> None:
    """Loop infinito que renova subscrições de webhook a cada 30 minutos.

    Roda como ``asyncio.Task`` no lifespan — não como ``BackgroundTasks``
    (que é request-scoped). Erros são logados e nunca propagados para
    evitar que o loop pare.
    """
    webhook_service = WebhookService()
    try:
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    await webhook_service.renew_subscriptions(db)
            except Exception:
                logger.exception(
                    "Erro no loop de renovação de webhooks [token=REDACTED]"
                )
            await asyncio.sleep(1800)  # 30 minutos
    finally:
        await webhook_service.close()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia startup e shutdown da aplicação.

    Startup:
        1. Inicializa conexão Redis
        2. Cria tabelas no banco (desenvolvimento)
        3. Inicia asyncio.Task para renewal_loop

    Shutdown:
        1. Cancela task de renovação
        2. Fecha conexão Redis
        3. Fecha engine do banco
    """
    # --- startup ---
    await init_redis()
    logger.info("Redis inicializado")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tabelas do banco criadas/verificadas")

    get_model()
    logger.info("Modelo de embeddings carregado")

    renewal_task = asyncio.create_task(renewal_loop())
    logger.info("Loop de renovação de webhooks iniciado")

    yield

    # --- shutdown ---
    renewal_task.cancel()
    try:
        await renewal_task
    except asyncio.CancelledError:
        pass
    logger.info("Loop de renovação de webhooks cancelado")

    await close_redis()
    logger.info("Redis fechado")

    await engine.dispose()
    logger.info("Engine do banco fechado")


# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lanez",
    description="Pipeline de dados do Microsoft 365",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware CORS — origens configuráveis via settings.CORS_ORIGINS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(graph.router)
app.include_router(mcp.router)
app.include_router(briefings.router)
app.include_router(voice.router)
app.include_router(memories.router)
app.include_router(status.router)
