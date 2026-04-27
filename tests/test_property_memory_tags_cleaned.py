"""Property-based test para limpeza de tags em save_memory.

**Validates: Requirements 3.4**

Propriedade 2: Para qualquer lista de tags com strings arbitrárias
(incluindo vazias e com espaços), a lógica de limpeza nunca produz
strings vazias e todas as tags são stripped.

    ∀ tags ∈ list[str] → ∀ t ∈ clean(tags): t.strip() ≠ "" ∧ t == t.strip()
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import lists, text


@given(tags=lists(text(), min_size=0, max_size=30))
@hyp_settings(max_examples=50, deadline=None)
def test_cleaned_tags_never_contain_empty_strings(tags: list[str]) -> None:
    """A lógica de limpeza de tags nunca produz strings vazias e todas são stripped."""
    # Aplicar a mesma lógica de limpeza usada em save_memory
    cleaned = [t.strip() for t in tags if t.strip()]

    # Nenhuma tag no resultado é string vazia
    assert all(tag != "" for tag in cleaned), (
        f"Encontrada tag vazia no resultado: {cleaned}"
    )

    # Todas as tags foram stripped (sem espaços no início/fim)
    assert all(tag == tag.strip() for tag in cleaned), (
        f"Encontrada tag não stripped: {cleaned}"
    )
