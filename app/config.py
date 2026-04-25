from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuração centralizada da aplicação Lanez.

    Campos obrigatórios (sem valor padrão) causam falha na inicialização
    se a variável de ambiente correspondente não estiver definida.
    """

    # Microsoft Entra ID — obrigatórios
    MICROSOFT_CLIENT_ID: str
    MICROSOFT_CLIENT_SECRET: str
    MICROSOFT_TENANT_ID: str

    # Segurança — obrigatórios
    SECRET_KEY: str
    WEBHOOK_CLIENT_STATE: str

    # Microsoft Entra ID — com valor padrão
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    # URL pública onde a Graph API entregará notificações de webhook
    WEBHOOK_NOTIFICATION_URL: str = "http://localhost:8000/webhooks/graph"

    # Banco de Dados
    DATABASE_URL: str = "postgresql+asyncpg://lanez:lanez@localhost:5432/lanez"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # SearXNG (busca web self-hosted)
    SEARXNG_URL: str = "http://localhost:8080"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
