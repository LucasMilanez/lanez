"""Caso de Borda 9: Variável de ambiente obrigatória ausente (R17 / 17.2).

Verifica que instanciar Settings sem MICROSOFT_CLIENT_ID lança ValidationError.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError


def test_settings_missing_microsoft_client_id_raises_validation_error(monkeypatch):
    """Settings() sem MICROSOFT_CLIENT_ID deve lançar ValidationError.

    Usa monkeypatch para remover a variável do ambiente e instancia
    Settings diretamente (não o singleton do módulo).
    """
    from app.config import Settings

    # Remover MICROSOFT_CLIENT_ID do ambiente
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)

    # Garantir que as demais variáveis obrigatórias estão presentes
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "test-tenant")
    monkeypatch.setenv("SECRET_KEY", "test-key")
    monkeypatch.setenv("WEBHOOK_CLIENT_STATE", "test-state")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    # Confirmar que o erro menciona o campo ausente
    errors = exc_info.value.errors()
    field_names = [e["loc"][0] for e in errors]
    assert "MICROSOFT_CLIENT_ID" in field_names
