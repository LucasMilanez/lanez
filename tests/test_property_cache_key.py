"""Property-based test para formato de chave de cache.

**Validates: Requirements 12.5**

Propriedade 3: A chave de cache gerada deve sempre seguir o formato
``lanez:{user_id}:{service}``, garantindo isolamento entre usuários e serviços.

    cache_key(user_id, service).startswith("lanez:")
    AND cache_key(user_id, service).endswith(f":{service}")
    AND user_id in cache_key(user_id, service)
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import sampled_from, uuids

from app.schemas.graph import ServiceType
from app.services.cache import cache_key


@given(user_id=uuids(), service=sampled_from(ServiceType))
@hyp_settings(max_examples=200)
def test_cache_key_format(user_id, service) -> None:
    """Para qualquer UUID e ServiceType, cache_key deve seguir o formato lanez:{user_id}:{service}."""
    uid = str(user_id)
    svc = service.value
    key = cache_key(uid, svc)

    assert key.startswith("lanez:"), (
        f"Chave deve começar com 'lanez:': obtido={key!r}"
    )
    assert key.endswith(f":{svc}"), (
        f"Chave deve terminar com ':{svc}': obtido={key!r}"
    )
    assert uid in key, (
        f"Chave deve conter o user_id '{uid}': obtido={key!r}"
    )
    assert key == f"lanez:{uid}:{svc}", (
        f"Formato exato incorreto: esperado='lanez:{uid}:{svc}', obtido={key!r}"
    )
    parts = key.split(":")
    assert len(parts) == 3, (
        f"Chave deve ter exatamente 3 partes separadas por ':': obtido={parts}"
    )
