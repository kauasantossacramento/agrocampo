from django.urls import path

from . import api_views

urlpatterns = [
    path("", api_views.ver_carrinho, name="api_carrinho"),
    path("itens/", api_views.adicionar_item, name="api_carrinho_adicionar"),
    path("itens/<int:item_id>/", api_views.remover_item, name="api_carrinho_remover"),
]
