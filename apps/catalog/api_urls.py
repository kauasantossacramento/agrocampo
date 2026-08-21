from rest_framework.routers import DefaultRouter

from .api_views import CategoriaViewSet, EspecieViewSet, MarcaViewSet, ProdutoViewSet

router = DefaultRouter()
router.register("produtos", ProdutoViewSet, basename="produto")
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("marcas", MarcaViewSet, basename="marca")
router.register("especies", EspecieViewSet, basename="especie")

urlpatterns = router.urls
