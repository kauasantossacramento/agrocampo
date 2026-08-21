from rest_framework.routers import DefaultRouter

from .api_views import PedidoViewSet

router = DefaultRouter()
router.register("", PedidoViewSet, basename="pedido")

urlpatterns = router.urls
