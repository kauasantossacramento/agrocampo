from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.detalhe, name="detalhe"),
    path("adicionar/<slug:slug>/", views.adicionar, name="adicionar"),
    path("item/<int:item_id>/atualizar/", views.atualizar, name="atualizar"),
    path("item/<int:item_id>/remover/", views.remover, name="remover"),
    path("cupom/", views.aplicar_cupom, name="cupom"),
    path("checkout/", views.checkout, name="checkout"),
]
