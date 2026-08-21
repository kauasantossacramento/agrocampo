from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/lida/", views.marcar_lida, name="marcar_lida"),
    path("todas/", views.marcar_todas, name="marcar_todas"),
]
