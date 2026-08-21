from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/pular/", views.pular, name="pular"),
    path("<int:pk>/pausar/", views.pausar, name="pausar"),
    path("<int:pk>/retomar/", views.retomar, name="retomar"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/frequencia/", views.alterar_frequencia, name="frequencia"),
]
