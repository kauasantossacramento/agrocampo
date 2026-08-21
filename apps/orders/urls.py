from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<str:numero>/", views.detalhe, name="detalhe"),
    path("<str:numero>/estorno/", views.solicitar_estorno, name="estorno"),
    path("<str:numero>/cancelar/", views.cancelar, name="cancelar"),
]
