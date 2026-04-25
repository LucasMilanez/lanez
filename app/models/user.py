"""Modelo User com criptografia Fernet para tokens Microsoft.

Tokens de acesso e refresh são criptografados em repouso usando Fernet
com chave derivada de SECRET_KEY via PBKDF2HMAC.
"""

import base64
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.database import Base

# ---------------------------------------------------------------------------
# Derivação de chave Fernet a partir de SECRET_KEY via PBKDF2
# ---------------------------------------------------------------------------

_SALT = b"lanez-token-encryption-salt"


def _derive_fernet_key(secret: str) -> bytes:
    """Deriva uma chave Fernet (32 bytes base64url) de uma secret string."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    key = kdf.derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


_fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))


# ---------------------------------------------------------------------------
# Helpers de criptografia
# ---------------------------------------------------------------------------

def encrypt_token(plaintext: str) -> str:
    """Criptografa um token e retorna o ciphertext como string base64."""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """Descriptografa um ciphertext base64 e retorna o token original."""
    return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# Modelo SQLAlchemy
# ---------------------------------------------------------------------------


class User(Base):
    """Usuário autenticado via Microsoft Entra ID.

    Os tokens Microsoft são armazenados criptografados no banco via Fernet.
    Acesse sempre pelas propriedades ``microsoft_access_token`` e
    ``microsoft_refresh_token`` — elas criptografam/descriptografam
    de forma transparente. Os campos internos ``_microsoft_access_token``
    e ``_microsoft_refresh_token`` armazenam apenas o ciphertext e não
    devem ser acessados diretamente.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    # Campos internos: armazenam ciphertext. Nome da coluna no banco é preservado.
    # Acesse via propriedades microsoft_access_token / microsoft_refresh_token.
    _microsoft_access_token: Mapped[str] = mapped_column(
        "microsoft_access_token", Text, nullable=False
    )
    _microsoft_refresh_token: Mapped[str] = mapped_column(
        "microsoft_refresh_token", Text, nullable=False
    )
    token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # -- Propriedades públicas com criptografia transparente ----------------

    @property
    def microsoft_access_token(self) -> str:
        """Descriptografa e retorna o access_token em texto claro."""
        return decrypt_token(self._microsoft_access_token)

    @microsoft_access_token.setter
    def microsoft_access_token(self, value: str) -> None:
        """Criptografa e persiste o access_token."""
        self._microsoft_access_token = encrypt_token(value)

    @property
    def microsoft_refresh_token(self) -> str:
        """Descriptografa e retorna o refresh_token em texto claro."""
        return decrypt_token(self._microsoft_refresh_token)

    @microsoft_refresh_token.setter
    def microsoft_refresh_token(self, value: str) -> None:
        """Criptografa e persiste o refresh_token."""
        self._microsoft_refresh_token = encrypt_token(value)
