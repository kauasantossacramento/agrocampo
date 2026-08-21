from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers

from .models import ItemPedido, Pedido


class ItemPedidoSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    rotulo_frequencia = serializers.CharField(read_only=True)

    class Meta:
        model = ItemPedido
        fields = (
            "id", "nome_produto", "sku", "quantidade", "preco_unitario",
            "total", "recorrente", "frequencia_dias", "rotulo_frequencia",
        )


class PedidoSerializer(serializers.ModelSerializer):
    itens = ItemPedidoSerializer(many=True, read_only=True)
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Pedido
        fields = (
            "numero", "status", "status_rotulo", "subtotal", "desconto",
            "desconto_assinatura", "frete", "total", "endereco_texto",
            "codigo_rastreio", "motivo_recusa", "criado_em", "pago_em", "itens",
        )


class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "numero"

    def get_queryset(self):
        return (
            Pedido.objects.do_usuario(self.request.user)
            .exclude(status=Pedido.Status.RASCUNHO)
            .prefetch_related("itens")
        )
