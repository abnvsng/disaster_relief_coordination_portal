"""Three ways a report arrives by phone, and one screen to watch it happen."""
from __future__ import annotations

import uuid

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.relief.models import Channel

from .models import InboundMessage, OutboundMessage
from .parser import FORMAT_HELP
from .services import handle_inbound


def simulator(request):
    """A feature phone, on screen.

    This is how the SMS path is demonstrated without DLT registration:
    same parser, same service, same acknowledgement, different transport.
    """
    reply = None
    if request.method == "POST":
        result = handle_inbound(
            from_phone=request.POST.get("from_phone", "+919000000001").strip(),
            body=request.POST.get("body", ""),
            provider_message_id=f"SIM-{uuid.uuid4().hex[:16]}",
            channel=Channel.SMS,
            language=request.POST.get("language", "en"),
        )
        reply = result.reply

    return render(request, "gateway/simulator.html", {
        "reply": reply,
        "format_help": FORMAT_HELP,
        "outbox": OutboundMessage.objects.all()[:15],
        "inbox": InboundMessage.objects.all()[:15],
    })


@csrf_exempt
@require_POST
def twilio_sms_webhook(request):
    """Twilio posts here. Answers with TwiML so the citizen gets one reply."""
    result = handle_inbound(
        from_phone=request.POST.get("From", ""),
        body=request.POST.get("Body", ""),
        provider_message_id=request.POST.get("MessageSid", uuid.uuid4().hex),
        channel=Channel.SMS,
        language=request.POST.get("Language", "en"),
    )
    return HttpResponse(
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<Response><Message>{_escape(result.reply)}</Message></Response>",
        content_type="application/xml",
    )


@csrf_exempt
def twilio_ivr_webhook(request):
    """Voice intake for callers who cannot write.

    Step 1 asks for the habitation code and headcount on the keypad.
    Step 2 receives the digits and files exactly the same report an SMS would.
    """
    digits = request.POST.get("Digits", "")
    if not digits:
        return HttpResponse(
            "<?xml version='1.0' encoding='UTF-8'?><Response>"
            "<Gather numDigits='9' timeout='12' action='/gateway/ivr/' method='POST'>"
            "<Say language='hi-IN'>Rahat ke liye, apne gaon ka code aur "
            "parivar ke sadasyon ki sankhya dabaiye.</Say>"
            "</Gather>"
            "<Say>No input received. Goodbye.</Say></Response>",
            content_type="application/xml",
        )

    # Keypad digits map onto the same grammar the parser already speaks.
    code_digits, members = digits[:6], digits[6:] or "1"
    body = f"HELP DBG{code_digits[-3:]} {members} WTR,RTN"
    result = handle_inbound(
        from_phone=request.POST.get("From", ""),
        body=body,
        provider_message_id=request.POST.get("CallSid", uuid.uuid4().hex),
        channel=Channel.IVR,
        language="hi",
    )
    return HttpResponse(
        f"<?xml version='1.0' encoding='UTF-8'?><Response>"
        f"<Say language='hi-IN'>{_escape(result.reply)}</Say></Response>",
        content_type="application/xml",
    )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
