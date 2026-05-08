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

    # Allowlist de emails autorizados a fazer login (defesa em profundidade
    # contra erros de configuração no Azure Portal — multi-tenant, common, etc).
    # Comma-separated, case-insensitive. Vazio = sem restrição (qualquer
    # email que passar no OAuth entra). Recomendado em produção single-user.
    # Exemplo: ALLOWED_EMAILS="lucas@lanez.pt,admin@example.com"
    ALLOWED_EMAILS: str = ""

    # Salt usado para derivar a chave Fernet a partir de SECRET_KEY via PBKDF2.
    # Valor default preservado por compatibilidade com bancos existentes —
    # alterar QUEBRA a descriptografia de tokens Microsoft já armazenados
    # (force re-login de todos os users). Para um novo deploy, gere um salt
    # único com: python -c "import os,base64;print(base64.b64encode(os.urandom(16)).decode())"
    FERNET_SALT: str = "lanez-token-encryption-salt"

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

    # Anthropic API — obrigatório para Fase 5 (briefing automático)
    ANTHROPIC_API_KEY: str

    # Briefing — janela histórica de coleta de contexto (em dias)
    BRIEFING_HISTORY_WINDOW_DAYS: int = 90

    # Groq Whisper — Fase 6b (voz)
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
    VOICE_MAX_AUDIO_BYTES: int = 5 * 1024 * 1024  # 5 MB
    VOICE_MAX_DURATION_SECONDS: int = 30

    # Audit log — Fase 7
    AUDIT_HISTORY_WINDOW_DAYS: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
