"""Property-based test para exponential backoff.

**Validates: Requisito 9 (9.3)**

Propriedade 6: O tempo de espera do exponential backoff deve dobrar a cada
tentativa consecutiva, começando em 1 segundo.

    backoff_time(n) == 2^(n-1)  para n de 1 a 3
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import integers

from app.services.graph import calculate_backoff


@given(attempt=integers(min_value=1, max_value=3))
@hyp_settings(max_examples=200)
def test_backoff_equals_power_of_two(attempt: int) -> None:
    """Para tentativa n (1-3), o backoff deve ser 2^(n-1) segundos."""
    expected = 2 ** (attempt - 1)
    result = calculate_backoff(attempt)
    assert result == expected, (
        f"Backoff incorreto para tentativa {attempt}: "
        f"esperado={expected}, obtido={result}"
    )


@given(attempt=integers(min_value=1, max_value=3))
@hyp_settings(max_examples=200)
def test_backoff_doubles_each_attempt(attempt: int) -> None:
    """Cada tentativa subsequente deve dobrar o tempo de espera."""
    if attempt == 1:
        assert calculate_backoff(attempt) == 1
    else:
        assert calculate_backoff(attempt) == 2 * calculate_backoff(attempt - 1)


def test_backoff_concrete_values() -> None:
    """Verifica os 3 valores concretos: 1s, 2s, 4s."""
    assert calculate_backoff(1) == 1
    assert calculate_backoff(2) == 2
    assert calculate_backoff(3) == 4
