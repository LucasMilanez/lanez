"""Property-based test para filtro de emails por attendees.

**Validates: Requirements 4.3**

Propriedade 1: Para qualquer lista de attendees e qualquer lista de emails
com from/to aleatórios, um email é mantido no resultado se e somente se
pelo menos um attendee aparece em from ou toRecipients.

Invariante bidirecional:
- ∀ email ∈ resultado → (email.from ∈ attendees) ∨ (∃ r ∈ email.to: r ∈ attendees)
- ∀ email ∉ resultado → (email.from ∉ attendees) ∧ (∀ r ∈ email.to: r ∉ attendees)
"""

from hypothesis import given, settings
from hypothesis.strategies import (
    emails,
    lists,
    tuples,
)

from app.services.briefing_context import filter_emails_by_attendees


def _build_email(from_addr: str, to_addrs: list[str]) -> dict:
    """Constrói email dict no formato Graph API."""
    return {
        "from": {"emailAddress": {"address": from_addr}},
        "toRecipients": [
            {"emailAddress": {"address": addr}} for addr in to_addrs
        ],
    }


# Estratégia: gerar lista de attendees (emails) e lista de (from, [to]) tuples
email_strategy = emails()
attendees_strategy = lists(email_strategy, min_size=0, max_size=8)
email_entry_strategy = tuples(
    email_strategy,
    lists(email_strategy, min_size=0, max_size=4),
)
email_list_strategy = lists(email_entry_strategy, min_size=0, max_size=10)


@given(
    attendees=attendees_strategy,
    email_entries=email_list_strategy,
)
@settings(max_examples=100, deadline=None)
def test_property_briefing_context_attendee_filter(
    attendees: list[str],
    email_entries: list[tuple[str, list[str]]],
) -> None:
    """Invariante bidirecional do filtro de attendees.

    Todo email no resultado tem pelo menos 1 attendee em from/to,
    e todo email fora do resultado não tem nenhum attendee em from/to.
    """
    attendees_set = set(attendees)
    email_dicts = [_build_email(from_addr, to_addrs) for from_addr, to_addrs in email_entries]

    result = filter_emails_by_attendees(email_dicts, attendees_set)
    result_set = set(id(e) for e in result)

    # Direção 1: todo email no resultado tem pelo menos 1 attendee em from/to
    for email in result:
        from_addr = email["from"]["emailAddress"]["address"]
        to_addrs = [r["emailAddress"]["address"] for r in email["toRecipients"]]
        assert from_addr in attendees_set or any(
            a in attendees_set for a in to_addrs
        ), (
            f"Email no resultado sem attendee: from={from_addr}, to={to_addrs}, "
            f"attendees={attendees_set}"
        )

    # Direção 2: todo email fora do resultado NÃO tem nenhum attendee em from/to
    for email in email_dicts:
        if id(email) not in result_set:
            from_addr = email["from"]["emailAddress"]["address"]
            to_addrs = [r["emailAddress"]["address"] for r in email["toRecipients"]]
            assert from_addr not in attendees_set and all(
                a not in attendees_set for a in to_addrs
            ), (
                f"Email fora do resultado com attendee: from={from_addr}, to={to_addrs}, "
                f"attendees={attendees_set}"
            )
