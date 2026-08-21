from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("newsletter/", views.newsletter, name="newsletter"),
    path("offline/", views.offline, name="offline"),
    path("pagina/<slug:slug>/", views.pagina, name="pagina"),
]
