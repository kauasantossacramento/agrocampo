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
    path("produtos/novo/form/", views.produto_form, name="produto_form_novo"),
    path("produtos/novo/salvar/", views.produto_salvar, name="produto_salvar_novo"),
    path("produtos/<int:produto_id>/form/", views.produto_form, name="produto_form"),
    path("produtos/<int:produto_id>/salvar-wizard/", views.produto_salvar, name="produto_salvar"),
    path("fotos/<int:imagem_id>/remover/", views.produto_remover_foto, name="produto_remover_foto"),
    path("configuracoes/<str:secao>/salvar/", views.salvar_config, name="salvar_config"),
    path("provedores/<int:provedor_id>/salvar/", views.salvar_provedor, name="salvar_provedor"),
    path("estoque/", views.estoque, name="estoque"),
    path("estoque/<int:produto_id>/repor/", views.repor_estoque, name="repor_estoque"),
    path("metricas/", views.metricas, name="metricas"),
    path("assinaturas/", views.assinaturas, name="assinaturas"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("conteudo/<slug:slug>/", views.gestao, name="gestao"),
    path("conteudo/<slug:slug>/novo/", views.gestao_form, name="gestao_form_novo"),
    path("conteudo/<slug:slug>/novo/salvar/", views.gestao_salvar, name="gestao_salvar_novo"),
    path("conteudo/<slug:slug>/<int:pk>/", views.gestao_form, name="gestao_form"),
    path("conteudo/<slug:slug>/<int:pk>/salvar/", views.gestao_salvar, name="gestao_salvar"),
    path("conteudo/<slug:slug>/<int:pk>/excluir/", views.gestao_excluir, name="gestao_excluir"),
    path("auditoria/<slug:tipo>/", views.auditoria, name="auditoria"),
    path("notificacoes/lidas/", views.marcar_notificacoes_lidas, name="notificacoes_lidas"),
]
