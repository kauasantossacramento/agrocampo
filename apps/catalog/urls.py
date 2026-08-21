from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("catalogo/", views.catalogo, name="catalogo"),
    path("busca/", views.catalogo, name="busca"),
    path("marcas/", views.marcas, name="marcas"),
    path("especies/", views.especies, name="especies"),
    path("categoria/<slug:slug>/", views.por_categoria, name="categoria"),
    path("marca/<slug:slug>/", views.por_marca, name="marca"),
    path("especie/<slug:slug>/", views.por_especie, name="especie"),
    path("produto/<slug:slug>/", views.detalhe_produto, name="produto"),
    path("produto/<slug:slug>/avaliar/", views.avaliar, name="avaliar"),
    path("produto/<slug:slug>/desejo/", views.alternar_desejo, name="desejo"),
]
