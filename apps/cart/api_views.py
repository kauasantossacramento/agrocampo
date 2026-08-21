from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.catalog.models import Produto

from .services import obter_carrinho


def _serializar(carrinho):
    if not carrinho:
        return {"itens": [], "quantidade": 0, "total": "0.00"}
    return {
        "id": carrinho.id,
        "itens": [
            {
                "id": i.id,
                "produto": i.produto.slug,
                "nome": i.produto.nome,
                "quantidade": i.quantidade,
                "preco_unitario": str(i.preco_unitario),
                "total": str(i.total),
                "recorrente": i.recorrente,
                "frequencia_dias": i.frequencia_dias,
            }
            for i in carrinho.linhas
        ],
        "quantidade": carrinho.quantidade_itens,
        "subtotal": str(carrinho.subtotal),
        "desconto_assinatura": str(carrinho.desconto_assinatura),
        "desconto_cupom": str(carrinho.desconto_cupom),
        "frete": str(carrinho.frete),
        "total": str(carrinho.total),
    }


@api_view(["GET"])
def ver_carrinho(request):
    return Response(_serializar(obter_carrinho(request, criar=False)))


@api_view(["POST"])
def adicionar_item(request):
    produto = Produto.objects.publicados().filter(slug=request.data.get("produto")).first()
    if not produto:
        return Response({"erro": "Produto não encontrado."}, status=404)

    quantidade = int(request.data.get("quantidade", 1))
    if produto.estoque < quantidade:
        return Response({"erro": "Estoque insuficiente."}, status=400)

    carrinho = obter_carrinho(request)
    recorrente = bool(request.data.get("recorrente")) and produto.permite_assinatura
    carrinho.adicionar(
        produto,
        quantidade,
        recorrente,
        int(request.data.get("frequencia", 30)) if recorrente else None,
    )
    return Response(_serializar(carrinho), status=201)


@api_view(["DELETE"])
def remover_item(request, item_id):
    carrinho = obter_carrinho(request, criar=False)
    if carrinho:
        carrinho.itens.filter(pk=item_id).delete()
    return Response(_serializar(carrinho))
