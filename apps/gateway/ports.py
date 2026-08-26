"""The MessageGateway port and its two adapters.

Dependency inversion, made concrete: ReliefService and the views depend on
the abstract MessageGateway. Swapping MockSMSGateway for TwilioGateway is a
one line change in settings and no caller is edited.

Why the mock is the default and not an afterthought:
sending A2P SMS to Indian numbers needs DLT registration with a telecom
operator under the TRAI regulations, which a student project cannot get.
The mock keeps the whole flow demonstrable end to end; the Twilio adapter
is real code, ready the day credentials exist.
"""
from __future__ import annotations

import abc

from django.conf import settings

from .models import OutboundMessage

# Acknowledgement copy, keyed by language. Short enough for one SMS segment.
ACK_TEMPLATES = {
    "en": (
        "Request #{id} recorded. Priority {priority}. "
        "Help is planned within {sla} hours. Reply STATUS {id} for an update."
    ),
    "hi": (
        "Anurodh #{id} darj hua. Prathmikta {priority}. "
        "Sahayata {sla} ghante mein. Sthiti ke liye STATUS {id} bhejein."
    ),
    "bn": (
        "Anurodh #{id} nathibhukto. অগ্রাধিকার {priority}. "
        "Sahajya {sla} ghontar modhye. Obostha jante STATUS {id} pathan."
    ),
}

REJECT_TEMPLATES = {
    "en": "Report not accepted: {reason}",
    "hi": "Report darj nahi hui: {reason}",
    "bn": "Report grohon kora hoyni: {reason}",
}


class MessageGateway(abc.ABC):
    """The port. Nothing above this line knows a telecom vendor exists."""

    name = "abstract"

    @abc.abstractmethod
    def send(self, to_phone: str, body: str, *, language: str = "en", request=None) -> bool:
        """Return True when the message was handed to the carrier."""

    def outbox(self, limit: int = 50):
        return OutboundMessage.objects.filter(backend=self.name)[:limit]


class MockSMSGateway(MessageGateway):
    """Writes to the database instead of the network. Free, offline, auditable.

    Numbers added to `fail_numbers` bounce, so the unhappy path is testable
    without waiting for a real carrier to fail.
    """

    name = "mock"
    fail_numbers: set[str] = set()

    def send(self, to_phone: str, body: str, *, language: str = "en", request=None) -> bool:
        failed = to_phone in self.fail_numbers
        OutboundMessage.objects.create(
            to_phone=to_phone,
            body=body,
            language=language,
            request=request,
            backend=self.name,
            delivered=not failed,
            error="carrier rejected the number" if failed else "",
        )
        return not failed


class TwilioGateway(MessageGateway):
    """Real carrier adapter. Reads credentials from the environment only."""

    name = "twilio"

    def send(self, to_phone: str, body: str, *, language: str = "en", request=None) -> bool:
        record = OutboundMessage(
            to_phone=to_phone, body=body, language=language,
            request=request, backend=self.name,
        )
        try:
            from twilio.rest import Client  # imported lazily: optional dependency

            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                to=to_phone, from_=settings.TWILIO_FROM_NUMBER, body=body
            )
            record.delivered = True
        except Exception as exc:                      # carrier or credential failure
            record.delivered = False
            record.error = str(exc)[:240]
        record.save()
        return record.delivered


def get_gateway() -> MessageGateway:
    """Factory. The only place the choice of vendor is made."""
    if settings.SMS_BACKEND == "twilio":
        return TwilioGateway()
    return MockSMSGateway()


def acknowledgement_for(request, language: str | None = None) -> str:
    """Answer in the language this sender wrote in, not the language of
    whoever happened to file the request first."""
    language = language or request.reporter_language
    template = ACK_TEMPLATES.get(language, ACK_TEMPLATES["en"])
    return template.format(
        id=request.pk, priority=request.priority, sla=request.sla_hours
    )


def rejection_for(reason: str, language: str = "en") -> str:
    template = REJECT_TEMPLATES.get(language, REJECT_TEMPLATES["en"])
    return template.format(reason=reason)
