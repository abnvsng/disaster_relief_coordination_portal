from django.urls import path

from . import views

urlpatterns = [
    path("simulator/", views.simulator, name="sms_simulator"),
    path("sms/", views.twilio_sms_webhook, name="twilio_sms"),
    path("ivr/", views.twilio_ivr_webhook, name="twilio_ivr"),
]
