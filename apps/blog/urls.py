from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("categoria/<slug:slug>/", views.por_categoria, name="categoria"),
    path("<slug:slug>/", views.detalhe, name="post"),
]
