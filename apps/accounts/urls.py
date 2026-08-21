from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("entrar/", views.entrar, name="entrar"),
    path("cadastrar/", views.cadastrar, name="cadastrar"),
    path("sair/", views.sair, name="sair"),
    path("perfil/", views.perfil, name="perfil"),
    path("enderecos/", views.enderecos, name="enderecos"),
    path("enderecos/<int:pk>/remover/", views.remover_endereco, name="remover_endereco"),
    path("enderecos/<int:pk>/padrao/", views.definir_endereco_padrao, name="endereco_padrao"),
    path("desejos/", views.desejos, name="desejos"),
]
