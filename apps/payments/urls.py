from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("checkout/<str:numero>/", views.checkout, name="checkout"),
    path("pix/<int:pagamento_id>/", views.pix, name="pix"),
    path("pix/<int:pagamento_id>/status/", views.status_pagamento, name="status"),
    path("pix/<int:pagamento_id>/simular/", views.simular_pix, name="simular_pix"),
    path("webhook/stone/", views.webhook, name="webhook"),
    path("webhook/cielo/", views.webhook_cielo, name="webhook_cielo"),
    path("webhook/pagarme/", views.webhook_pagarme, name="webhook_pagarme"),
]
