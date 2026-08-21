"""Área do cliente: histórico de pedidos, status e pedido de estorno."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.payments.models import Estorno
from apps.payments.services import estornar

from .models import Pedido
from .services import devolver_estoque


@login_required
def lista(request):
    pedidos = (
        Pedido.objects.do_usuario(request.user)
        .exclude(status=Pedido.Status.RASCUNHO)
        .prefetch_related("itens__produto__imagens")
    )
    pagina = Paginator(pedidos, 10).get_page(request.GET.get("pagina"))
    return render(request, "orders/lista.html", {"pagina": pagina, "pedidos": pagina.object_list})


@login_required
def detalhe(request, numero):
    pedido = get_object_or_404(
        Pedido.objects.prefetch_related("itens__produto__imagens", "eventos__autor"),
        numero=numero,
        usuario=request.user,
    )
    similares = []
    if pedido.status == Pedido.Status.RECUSADO:
        # sugestões para substituir o item que faltou
        for item in pedido.itens.select_related("produto")[:2]:
            similares.extend(item.produto.similares(3))

    return render(
        request,
        "orders/detalhe.html",
        {
            "pedido": pedido,
            "pagamento": pedido.pagamento_atual,
            "eventos": pedido.eventos.all(),
            "similares": similares[:3],
            "estorno": Estorno.objects.filter(pagamento__pedido=pedido).first(),
        },
    )


@login_required
@require_POST
def solicitar_estorno(request, numero):
    pedido = get_object_or_404(Pedido, numero=numero, usuario=request.user)
    pagamento = pedido.pagamento_atual

    if not pedido.pode_ser_estornado:
        messages.error(request, "Este pedido não tem valor disponível para estorno.")
        return redirect(pedido.get_absolute_url())

    motivo = (
        Estorno.Motivo.PEDIDO_RECUSADO
        if pedido.status == Pedido.Status.RECUSADO
        else Estorno.Motivo.DESISTENCIA
    )
    resultado = estornar(pagamento, motivo=motivo, autor=request.user)

    if resultado.status == Estorno.Status.CONCLUIDO:
        devolver_estoque(pedido, motivo="Estorno solicitado pelo cliente")
        if pedido.pode_ir_para(Pedido.Status.ESTORNADO):
            pedido.mudar_status(
                Pedido.Status.ESTORNADO,
                autor=request.user,
                titulo="Estorno solicitado",
                descricao=f"R$ {resultado.valor} retornam em até 5 dias úteis.",
            )
        messages.success(
            request,
            f"Estorno de R$ {resultado.valor} solicitado. "
            "O valor retorna ao seu meio de pagamento em até 5 dias úteis.",
        )
    else:
        messages.error(request, "Não conseguimos processar o estorno. Fale com o suporte.")
    return redirect(pedido.get_absolute_url())


@login_required
@require_POST
def cancelar(request, numero):
    pedido = get_object_or_404(Pedido, numero=numero, usuario=request.user)
    if not pedido.pode_ir_para(Pedido.Status.CANCELADO):
        messages.error(request, "Este pedido não pode mais ser cancelado.")
        return redirect(pedido.get_absolute_url())

    devolver_estoque(pedido, motivo="Cancelamento pelo cliente")
    pedido.mudar_status(
        Pedido.Status.CANCELADO,
        autor=request.user,
        titulo="Pedido cancelado",
        descricao="Cancelado pelo cliente.",
    )
    messages.success(request, "Pedido cancelado.")
    return redirect("orders:lista")
