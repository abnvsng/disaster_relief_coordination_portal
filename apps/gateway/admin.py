from django.contrib import admin

from .models import InboundMessage, OutboundMessage


@admin.register(OutboundMessage)
class OutboundAdmin(admin.ModelAdmin):
    list_display = ("to_phone", "language", "backend", "delivered", "sent_at")
    list_filter = ("backend", "delivered", "language")


@admin.register(InboundMessage)
class InboundAdmin(admin.ModelAdmin):
    list_display = ("from_phone", "channel", "accepted", "received_at")
    list_filter = ("channel", "accepted")
