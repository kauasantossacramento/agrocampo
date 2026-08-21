"""Carrinho e checkout."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Produto
from apps.orders.models import Cupom
from apps.orders.services import EstoqueInsuficiente, criar_pedido_do_carrinho
from apps.payments.models import ProvedorPagamento

from .models import ItemCarrinho
from .services import obter_carrinho


def _resposta(request, carrinho, mensagem, ok=True, destino="cart:detalhe"):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": ok,
                "mensagem": mensagem,
                "quantidade": carrinho.quantidade_itens if carrinho else 0,
                "total": str(carrinho.total) if carrinho else "0",
            }
        )
    (messages.success if ok else messages.error)(request, mensagem)
    return redirect(request.META.get("HTTP_REFERER", destino) if ok else destino)


def detalhe(request):
    carrinho = obter_carrinho(request)
    provedor = ProvedorPagamento.ativo_padrao()
    return render(
        request,
        "cart/carrinho.html",
        {
            "carrinho": carrinho,
            "provedor": provedor,
            "metodos": provedor.metodos_disponiveis(),
            "parcelas": provedor.parcelas_disponiveis(carrinho.total) if carrinho else [],
        },
    )


@require_POST
def adicionar(request, slug):
    produto = get_object_or_404(Produto.objects.publicados(), slug=slug)
    carrinho = obter_carrinho(request)

    quantidade = max(1, int(request.POST.get("quantidade", 1)))
    recorrente = request.POST.get("recorrente") == "1" and produto.permite_assinatura
    frequencia = int(request.POST.get("frequencia", 30)) if recorrente else None

    if produto.estoque < quantidade:
        return _resposta(request, carrinho, f"{produto.nome} está sem estoque.", ok=False)

    carrinho.adicionar(produto, quantidade, recorrente, frequencia)
    return _resposta(request, carrinho, f"{produto.nome} foi para o carrinho.")


@require_POST
def atualizar(request, item_id):
    carrinho = obter_carrinho(request)
    item = get_object_or_404(ItemCarrinho, pk=item_id, carrinho=carrinho)

    # `ajuste` (-1/+1) vem dos botões; `quantidade` vem de quem digitou.
    # O ajuste parte do valor no banco, não do campo enviado — assim dois
    # cliques rápidos não se anulam por causa de um valor desatualizado.
    ajuste = request.POST.get("ajuste")
    if ajuste is not None:
        try:
            quantidade = item.quantidade + int(ajuste)
        except ValueError:
            quantidade = item.quantidade
    else:
        try:
            quantidade = int(request.POST.get("quantidade", 1))
        except ValueError:
            return _resposta(request, carrinho, "Quantidade inválida.", ok=False)

    if quantidade <= 0:
        item.delete()
        return _resposta(request, carrinho, "Item removido do carrinho.")
    if quantidade > item.produto.estoque:
        return _resposta(
            request, carrinho,
            f"Temos apenas {item.produto.estoque} unidades em estoque.", ok=False,
        )

    item.quantidade = quantidade
    item.save(update_fields=["quantidade"])
    return _resposta(request, carrinho, "Carrinho atualizado.")


@require_POST
def remover(request, item_id):
    carrinho = obter_carrinho(request)
    get_object_or_404(ItemCarrinho, pk=item_id, carrinho=carrinho).delete()
    return _resposta(request, carrinho, "Item removido do carrinho.")


@require_POST
def aplicar_cupom(request):
    carrinho = obter_carrinho(request)
    codigo = (request.POST.get("cupom") or "").strip().upper()

    if not codigo:
        carrinho.cupom = None
        carrinho.save(update_fields=["cupom"])
        return _resposta(request, carrinho, "Cupom removido.")

    cupom = Cupom.objects.filter(codigo=codigo).first()
    if not cupom or not cupom.vigente():
        return _resposta(request, carrinho, "Cupom inválido ou expirado.", ok=False)
    if cupom.calcular(carrinho.subtotal) <= 0:
        return _resposta(
            request, carrinho,
            f"Este cupom vale para compras acima de R$ {cupom.valor_minimo}.", ok=False,
        )

    carrinho.cupom = cupom
    carrinho.save(update_fields=["cupom"])
    return _resposta(request, carrinho, f"Cupom {codigo} aplicado!")


@login_required
def checkout(request):
    carrinho = obter_carrinho(request)
    if carrinho.vazio:
        messages.info(request, "Seu carrinho está vazio.")
        return redirect("catalog:catalogo")

    provedor = ProvedorPagamento.ativo_padrao()

    if request.method == "POST":
        endereco_id = request.POST.get("endereco")
        endereco = request.user.enderecos.filter(pk=endereco_id).first()
        if not endereco:
            messages.error(request, "Escolha um endereço de entrega.")
            return redirect("cart:checkout")
        try:
            pedido = criar_pedido_do_carrinho(
                carrinho, request.user, endereco, request.POST.get("observacoes", "")
            )
        except EstoqueInsuficiente as exc:
            messages.error(request, str(exc))
            return redirect("cart:detalhe")

        carrinho.finalizado = True
        carrinho.save(update_fields=["finalizado"])
        return redirect("payments:checkout", numero=pedido.numero)

    return render(
        request,
        "cart/checkout.html",
        {
            "carrinho": carrinho,
            "enderecos": request.user.enderecos.all(),
            "provedor": provedor,
        },
    )
