"""Property-based test para TTL por serviço.

**Validates: Requisito 12 (12.1, 12.2, 12.3, 12.4)**

Propriedade 2: O TTL atribuído a cada serviço deve ser sempre o valor correto:
300s para calendar/mail, 900s para onenote/onedrive.

    get_ttl("calendar") == 300
    get_ttl("mail") == 300
    get_ttl("onenote") == 900
    get_ttl("onedrive") == 900
"""

from hypothesis import given, settings as hyp_settings
from hypothesis.strategies import sampled_from

from app.schemas.graph import ServiceType
from app.services.cache import get_ttl

EXPECTED_TTL = {
    ServiceType.CALENDAR: 300,
    ServiceType.MAIL: 300,
    ServiceType.ONENOTE: 900,
    ServiceType.ONEDRIVE: 900,
}


@given(service=sampled_from(ServiceType))
@hyp_settings(max_examples=200)
def test_ttl_matches_expected_value(service: ServiceType) -> None:
    """Para qualquer ServiceType, get_ttl deve retornar o TTL esperado."""
    ttl = get_ttl(service)
    expected = EXPECTED_TTL[service]
    assert ttl == expected, (
        f"TTL incorreto para {service.value}: esperado={expected}, obtido={ttl}"
    )


@given(service=sampled_from([ServiceType.CALENDAR, ServiceType.MAIL]))
@hyp_settings(max_examples=100)
def test_high_frequency_services_have_short_ttl(service: ServiceType) -> None:
    """Calendar e mail (alta frequência de mudança) devem ter TTL de 5 min."""
    assert get_ttl(service) == 300


@given(service=sampled_from([ServiceType.ONENOTE, ServiceType.ONEDRIVE]))
@hyp_settings(max_examples=100)
def test_low_frequency_services_have_long_ttl(service: ServiceType) -> None:
    """OneNote e OneDrive (baixa frequência de mudança) devem ter TTL de 15 min."""
    assert get_ttl(service) == 900
