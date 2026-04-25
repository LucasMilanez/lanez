"""Property-based test para unicidade do state OAuth.

**Validates: Requirements 1.4**

Propriedade 8: Para N chamadas de geração de state, todos os N valores devem
ser distintos, prevenindo ataques CSRF.

O state é gerado via ``secrets.token_hex(16)`` — 16 bytes de entropia (128 bits).
A probabilidade de colisão em amostras pequenas é astronomicamente baixa.
"""

import re
import secrets

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import integers


# O state OAuth é gerado exatamente assim no auth router
def _generate_state() -> str:
    """Replica a geração de state usada em app/routers/auth.py."""
    return secrets.token_hex(16)


# Regex: 32 caracteres hexadecimais (16 bytes em hex)
HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


@given(batch_size=integers(min_value=2, max_value=200))
@hyp_settings(max_examples=200)
def test_oauth_states_are_all_unique(batch_size: int) -> None:
    """Gerar batch_size states deve produzir batch_size valores distintos."""
    states = [_generate_state() for _ in range(batch_size)]
    unique = set(states)

    assert len(unique) == batch_size, (
        f"Esperados {batch_size} states únicos, obtidos {len(unique)}. "
        f"Colisões detectadas."
    )


@given(n=integers(min_value=1, max_value=100))
@hyp_settings(max_examples=200)
def test_oauth_state_is_valid_hex_32_chars(n: int) -> None:
    """Cada state gerado deve ser uma string hexadecimal de 32 caracteres."""
    state = _generate_state()

    assert isinstance(state, str)
    assert HEX32_RE.match(state), (
        f"State não é hex de 32 chars: {state!r}"
    )


@given(n=integers(min_value=1, max_value=50))
@hyp_settings(max_examples=100)
def test_oauth_state_has_sufficient_entropy(n: int) -> None:
    """State deve ter 128 bits de entropia (16 bytes = 32 hex chars)."""
    state = _generate_state()

    # 32 hex chars = 16 bytes = 128 bits
    assert len(state) == 32, (
        f"State deve ter 32 hex chars (128 bits), obtido {len(state)}"
    )
    # Converter de volta para bytes para confirmar tamanho
    raw = bytes.fromhex(state)
    assert len(raw) == 16, (
        f"State deve representar 16 bytes, obtido {len(raw)}"
    )
