from rest_framework import filters, viewsets

from .models import Categoria, Especie, Marca, Produto
from .serializers import (
    CategoriaSerializer,
    EspecieSerializer,
    MarcaSerializer,
    ProdutoDetalheSerializer,
    ProdutoSerializer,
)


class ProdutoViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo consumido pelo PWA/app mobile."""

    lookup_field = "slug"
    serializer_class = ProdutoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "resumo", "descricao", "sku", "categoria__nome", "marca__nome"]
    ordering_fields = ["preco", "vendas", "criado_em"]

    def get_queryset(self):
        qs = Produto.objects.vitrine()
        params = self.request.query_params
        if categoria := params.get("categoria"):
            qs = qs.filter(categoria__slug=categoria)
        if marca := params.get("marca"):
            qs = qs.filter(marca__slug=marca)
        if especie := params.get("especie"):
            qs = qs.filter(especies__slug=especie)
        if params.get("assinatura") == "1":
            qs = qs.filter(permite_assinatura=True)
        if params.get("promocao") == "1":
            qs = qs.filter(preco_promocional__isnull=False)
        if params.get("destaque") == "1":
            qs = qs.filter(destaque=True)
        # ordenacao explicita: sem ela a paginacao do DRF fica instavel
        return qs.order_by("-destaque", "-vendas", "-id")

    def get_serializer_class(self):
        return ProdutoDetalheSerializer if self.action == "retrieve" else ProdutoSerializer


class CategoriaViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    serializer_class = CategoriaSerializer
    queryset = Categoria.objects.publicados()


class MarcaViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    serializer_class = MarcaSerializer
    queryset = Marca.objects.publicados()


class EspecieViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    serializer_class = EspecieSerializer
    queryset = Especie.objects.publicados()
