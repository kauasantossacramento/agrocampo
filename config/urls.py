from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("conta/", include("apps.accounts.urls")),
    path("carrinho/", include("apps.cart.urls")),
    path("pedidos/", include("apps.orders.urls")),
    path("pagamentos/", include("apps.payments.urls")),
    path("assinaturas/", include("apps.subscriptions.urls")),
    path("notificacoes/", include("apps.notifications.urls")),
    path("painel/", include("apps.dashboard.urls")),
    path("blog/", include("apps.blog.urls")),
    path("entrega/", include("apps.shipping.urls")),
    path("api/v1/", include("config.api_urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "AgroCampo — Administracao"
admin.site.site_title = "AgroCampo"
admin.site.index_title = "Gestao da loja"
