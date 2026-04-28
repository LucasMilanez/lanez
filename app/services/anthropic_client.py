"""Cliente Anthropic para geração de briefings com prompt caching.

Encapsula chamada ao Claude Haiku 4.5 com cache_control ephemeral
no system prompt e captura de telemetria de tokens (incluindo cache).
"""

from __future__ import annotations

from dataclasses import dataclass

from anthropic import AsyncAnthropic

from app.config import settings

_MODEL_ID = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1500

_client: AsyncAnthropic | None = None


@dataclass
class BriefingResult:
    """Resultado da geração de briefing com telemetria de tokens."""

    content: str
    model: str
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int


def get_anthropic_client() -> AsyncAnthropic:
    """Retorna cliente Anthropic singleton.

    Inicializa na primeira chamada com ``settings.ANTHROPIC_API_KEY``.
    Reutiliza a mesma instância nas chamadas subsequentes para evitar
    criar conexão a cada request.
    """
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def generate_briefing_text(
    system_prompt: str,
    user_content: str,
) -> BriefingResult:
    """Chama Claude Haiku 4.5 com cache_control ephemeral no system prompt.

    O system prompt é marcado com ``cache_control: {"type": "ephemeral"}``
    para que a Anthropic o mantenha em cache por ~5 min, reduzindo custo
    em ~90% para input tokens cacheados a partir do 2º briefing na janela.

    Args:
        system_prompt: Prompt de sistema fixo (pt-BR, ~2k tokens).
        user_content: Conteúdo do usuário com contexto da reunião.

    Returns:
        BriefingResult com conteúdo gerado e telemetria de tokens.
    """
    client = get_anthropic_client()

    response = await client.messages.create(
        model=_MODEL_ID,
        max_tokens=_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    return BriefingResult(
        content=response.content[0].text,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        output_tokens=response.usage.output_tokens,
    )
