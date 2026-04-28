"""Testes do cliente Anthropic para geração de briefings.

Todos os testes mockam a API — JAMAIS chamam a Anthropic real.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.anthropic_client import generate_briefing_text


def _make_mock_response(
    text: str = "Briefing gerado",
    model: str = "claude-haiku-4-5-20251001",
    input_tokens: int = 200,
    output_tokens: int = 150,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> MagicMock:
    """Cria mock de resposta da Anthropic API."""
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    response.content = [content_block]
    response.model = model
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.usage.cache_read_input_tokens = cache_read_input_tokens
    response.usage.cache_creation_input_tokens = cache_creation_input_tokens
    return response


@pytest.mark.asyncio
async def test_anthropic_client_uses_cache_control():
    """Verifica que o system prompt é enviado com cache_control ephemeral."""
    mock_response = _make_mock_response()
    mock_create = AsyncMock(return_value=mock_response)

    with patch(
        "app.services.anthropic_client.get_anthropic_client"
    ) as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        mock_get_client.return_value = mock_client

        await generate_briefing_text("system", "user")

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_anthropic_client_captures_cache_tokens():
    """Verifica captura de cache_read_tokens e cache_write_tokens da resposta."""
    mock_response = _make_mock_response(
        cache_read_input_tokens=100,
        cache_creation_input_tokens=50,
    )
    mock_create = AsyncMock(return_value=mock_response)

    with patch(
        "app.services.anthropic_client.get_anthropic_client"
    ) as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        mock_get_client.return_value = mock_client

        result = await generate_briefing_text("system", "user")

    assert result.cache_read_tokens == 100
    assert result.cache_write_tokens == 50
