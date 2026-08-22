from django.urls import path

from . import views

app_name = "shipping"

urlpatterns = [
    path("onde-entregamos/", views.onde_entregamos, name="onde_entregamos"),
]
