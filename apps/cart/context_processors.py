from .services import obter_carrinho


def cart_context(request):
    carrinho = obter_carrinho(request, criar=False)
    return {
        "carrinho": carrinho,
        "carrinho_qtd": carrinho.quantidade_itens if carrinho else 0,
    }
