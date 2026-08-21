"""Rotas da API v1 (consumidas pelo PWA/app mobile)."""
from django.urls import include, path

urlpatterns = [
    path("catalogo/", include("apps.catalog.api_urls")),
    path("carrinho/", include("apps.cart.api_urls")),
    path("pedidos/", include("apps.orders.api_urls")),
    path("notificacoes/", include("apps.notifications.api_urls")),
]
