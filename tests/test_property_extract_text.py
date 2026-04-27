"""Property-based test para extract_text.

**Validates: Requisito 4.7 (extract_text NEVER levanta exceção)**

Propriedade 8: Para qualquer serviço válido e qualquer dict como data,
extract_text deve sempre retornar uma string sem levantar exceção.

    isinstance(extract_text(service, data), str)
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import (
    dictionaries,
    from_type,
    just,
    lists,
    none,
    one_of,
    recursive,
    sampled_from,
    text,
)

from app.services.embeddings import extract_text

VALID_SERVICES = ["calendar", "mail", "onenote", "onedrive"]

# Estratégia recursiva que gera valores JSON arbitrários (str, int, float,
# bool, None, listas e dicts aninhados) — simula payloads inesperados da
# Graph API.
_json_primitives = one_of(text(), from_type(int), from_type(float), from_type(bool), none())
json_values = recursive(
    _json_primitives,
    lambda children: one_of(
        lists(children, max_size=5),
        dictionaries(text(max_size=20), children, max_size=8),
    ),
    max_leaves=30,
)

random_data = dictionaries(text(max_size=30), json_values, max_size=10)


@given(
    service=sampled_from(VALID_SERVICES),
    data=random_data,
)
@hyp_settings(max_examples=200)
def test_extract_text_never_raises(service: str, data: dict) -> None:
    """extract_text deve retornar string sem exceção para qualquer dict e serviço válido."""
    result = extract_text(service, data)

    assert isinstance(result, str), (
        f"Esperado str, obteve {type(result).__name__} "
        f"para service={service!r}"
    )


@given(service=text(min_size=1), data=random_data)
@hyp_settings(max_examples=50)
def test_extract_text_unknown_service_returns_empty(service: str, data: dict) -> None:
    """extract_text deve retornar string vazia para serviço desconhecido."""
    if service in VALID_SERVICES:
        return  # pula serviços válidos — testados acima

    result = extract_text(service, data)

    assert result == "", (
        f"Esperado string vazia para serviço desconhecido {service!r}, obteve {result!r}"
    )


@given(service=sampled_from(VALID_SERVICES), data=just({}))
@hyp_settings(max_examples=20)
def test_extract_text_empty_dict_returns_string(service: str, data: dict) -> None:
    """extract_text com dict vazio deve retornar string sem exceção."""
    result = extract_text(service, data)

    assert isinstance(result, str), (
        f"Esperado str, obteve {type(result).__name__}"
    )
