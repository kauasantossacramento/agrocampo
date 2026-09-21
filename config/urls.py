from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# O admin do Django é ferramenta do desenvolvedor: caminho próprio (configurável
# por DJANGO_ADMIN_PATH) e só para usuários com a marca `desenvolvedor`. O
# lojista tem o painel — nenhuma tela do sistema aponta para cá.
def _so_desenvolvedor(request):
    u = request.user
    return bool(u.is_active and u.is_superuser and getattr(u, "desenvolvedor", False))


admin.site.has_permission = _so_desenvolvedor

urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("conta/", include("apps.accounts.urls")),
    path("carrinho/", include("apps.cart.urls")),
    path("pedidos/", include("apps.orders.urls")),
    path("pagamentos/", include("apps.payments.urls")),
    path("assinaturas/", include("apps.subscriptions.urls")),
    path("notificacoes/", include("apps.notifications.urls")),
    path("painel/", include("apps.dashboard.urls")),
    path("blog/", include("apps.blog.urls")),
    path("entrega/", include("apps.shipping.urls")),
    path("assistente/", include("apps.assistant.urls")),
    path("api/v1/", include("config.api_urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "AgroCampo — Administracao"
admin.site.site_title = "AgroCampo"
admin.site.index_title = "Gestao da loja"
