"""One inbound path, shared by the simulator, the SMS webhook and IVR."""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.geo.models import Habitation
from apps.relief.models import Channel
from apps.relief.services import IntakeRejected, service as relief_service

from .models import InboundMessage
from .parser import ParseError, parser
from .ports import acknowledgement_for, get_gateway, rejection_for


@dataclass
class InboundResult:
    accepted: bool
    reply: str
    request = None


@transaction.atomic
def handle_inbound(
    *, from_phone: str, body: str, provider_message_id: str,
    channel: str = Channel.SMS, language: str = "en",
) -> InboundResult:
    """Parse, validate, create and acknowledge. Idempotent on provider id."""
    existing = InboundMessage.objects.filter(
        provider_message_id=provider_message_id
    ).first()
    if existing:
        # The carrier retried. Replay the original answer, do not file twice.
        return InboundResult(accepted=existing.accepted, reply=existing.reply)

    inbound = InboundMessage(
        provider_message_id=provider_message_id,
        from_phone=from_phone,
        body=body,
        channel=channel,
    )
    gateway = get_gateway()

    try:
        report = parser.parse_sms(body)
    except ParseError as exc:
        inbound.reply = rejection_for(str(exc), language)
        inbound.save()
        gateway.send(from_phone, inbound.reply, language=language)
        return InboundResult(accepted=False, reply=inbound.reply)

    habitation = Habitation.objects.filter(code=report.habitation_code).first()
    if habitation is None:
        inbound.reply = rejection_for(
            f"habitation code {report.habitation_code} is not on the district register.",
            language,
        )
        inbound.save()
        gateway.send(from_phone, inbound.reply, language=language)
        return InboundResult(accepted=False, reply=inbound.reply)

    try:
        result = relief_service.intake(
            habitation=habitation,
            needs=report.needs,
            channel=channel,
            reporter_phone=from_phone,
            reporter_language=language,
            total_members=report.total_members,
            water_depth_m=report.water_depth_m,
            people_trapped=report.people_trapped,
        )
    except IntakeRejected as exc:
        inbound.reply = rejection_for(str(exc), language)
        inbound.save()
        gateway.send(from_phone, inbound.reply, language=language)
        return InboundResult(accepted=False, reply=inbound.reply)

    target = result.duplicate_of or result.request
    inbound.request = target
    inbound.accepted = True
    inbound.reply = acknowledgement_for(target, language)
    inbound.save()
    gateway.send(from_phone, inbound.reply, language=language, request=target)

    out = InboundResult(accepted=True, reply=inbound.reply)
    out.request = target
    return out
