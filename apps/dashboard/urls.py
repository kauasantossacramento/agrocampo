from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("pedidos/", views.pedidos, name="pedidos"),
    path("pedidos/<str:numero>/", views.detalhe_pedido, name="pedido"),
    path("pedidos/<str:numero>/aprovar/", views.aprovar, name="aprovar"),
    path("pedidos/<str:numero>/recusar/", views.recusar, name="recusar"),
    path("pedidos/<str:numero>/enviar/", views.enviar, name="enviar"),
    path("produtos/", views.produtos, name="produtos"),
    path("produtos/<int:produto_id>/salvar/", views.salvar_produto_rapido, name="salvar_produto"),
    path("produtos/limpar/", views.limpar_catalogo_view, name="limpar_catalogo"),
    path("estoque/", views.estoque, name="estoque"),
    path("estoque/<int:produto_id>/repor/", views.repor_estoque, name="repor_estoque"),
    path("metricas/", views.metricas, name="metricas"),
    path("assinaturas/", views.assinaturas, name="assinaturas"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("notificacoes/lidas/", views.marcar_notificacoes_lidas, name="notificacoes_lidas"),
]
