"""Configuração global de testes.

Define variáveis de ambiente necessárias ANTES de importar módulos da app.
"""

import os


# Definir variáveis de ambiente obrigatórias para testes
os.environ.setdefault("MICROSOFT_CLIENT_ID", "test-client-id")
os.environ.setdefault("MICROSOFT_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("MICROSOFT_TENANT_ID", "test-tenant-id")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("WEBHOOK_CLIENT_STATE", "test-webhook-state")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://lanez:lanez@localhost:5432/lanez_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
