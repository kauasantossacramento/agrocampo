"""Painel do lojista: fila de aprovação, métricas, estoque e assinaturas."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Avg, Count, F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from decimal import Decimal, InvalidOperation

from apps.catalog.models import Categoria, Marca, MovimentoEstoque, Produto
from apps.notifications.models import Notificacao
from apps.orders.models import Pedido
from apps.orders.services import (
    EstoqueInsuficiente,
    aprovar_pedido,
    marcar_enviado,
    recusar_pedido,
)
from apps.payments.models import Pagamento, ProvedorPagamento
from apps.subscriptions.models import Assinatura

operador_requerido = user_passes_test(
    lambda u: u.is_authenticated and u.e_operador, login_url="accounts:entrar"
)


def _metricas():
    hoje = timezone.localdate()
    inicio = timezone.make_aware(
        timezone.datetime.combine(hoje, timezone.datetime.min.time())
    )
    pagos_hoje = Pedido.objects.faturados().filter(pago_em__gte=inicio)
    faturados = Pedido.objects.faturados()
    return {
        "vendas_hoje": pagos_hoje.aggregate(t=Sum("total"))["t"] or 0,
        "pedidos_hoje": pagos_hoje.count(),
        "pendentes": Pedido.objects.aguardando_aprovacao().count(),
        "ticket_medio": faturados.aggregate(t=Avg("total"))["t"] or 0,
        "assinaturas_ativas": Assinatura.objects.filter(
            status=Assinatura.Status.ATIVA
        ).count(),
        "estoque_critico": Produto.objects.filter(
            publicado=True, estoque__lte=F("estoque_minimo")
        ).count(),
    }


@operador_requerido
def painel(request):
    pedidos = (
        Pedido.objects.faturados()
        .select_related("usuario")
        .prefetch_related("itens")[:15]
    )
    numero = request.GET.get("pedido")
    selecionado = (
        Pedido.objects.filter(numero=numero).first()
        if numero
        else Pedido.objects.aguardando_aprovacao().first() or (pedidos[0] if pedidos else None)
    )
    return render(
        request,
        "dashboard/painel.html",
        {
            "secao": "painel",
            "metricas": _metricas(),
            "pedidos": pedidos,
            "selecionado": selecionado,
            "estoque_baixo": Produto.objects.filter(
                publicado=True, estoque__lte=F("estoque_minimo")
            ).order_by("estoque")[:8],
        },
    )


@operador_requerido
def pedidos(request):
    qs = Pedido.objects.select_related("usuario").prefetch_related("itens")
    status = request.GET.get("status")
    busca = request.GET.get("q", "").strip()
    if status:
        qs = qs.filter(status=status)
    if busca:
        qs = qs.filter(numero__icontains=busca) | qs.filter(nome_cliente__icontains=busca)
    return render(
        request,
        "dashboard/pedidos.html",
        {
            "secao": "painel",
            "pedidos": qs[:100],
            "status_escolhido": status,
            "busca": busca,
            "status_opcoes": Pedido.Status.choices,
            "metricas": _metricas(),
        },
    )


@operador_requerido
def detalhe_pedido(request, numero):
    pedido = get_object_or_404(
        Pedido.objects.prefetch_related("itens__produto", "eventos", "pagamentos"),
        numero=numero,
    )
    return render(
        request,
        "dashboard/pedido_detalhe.html",
        {
            "secao": "painel",
            "pedido": pedido,
            "pagamento": pedido.pagamento_atual,
            "faltantes": pedido.itens_indisponiveis,
        },
    )


@operador_requerido
@require_POST
def aprovar(request, numero):
    pedido = get_object_or_404(Pedido, numero=numero)
    try:
        aprovar_pedido(pedido, request.user)
        messages.success(request, f"{pedido.numero} aprovado. Cliente notificado.")
    except (EstoqueInsuficiente, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect(request.META.get("HTTP_REFERER", "dashboard:painel"))


@operador_requerido
@require_POST
def recusar(request, numero):
    pedido = get_object_or_404(Pedido, numero=numero)
    motivo = request.POST.get("motivo") or "Produto sem estoque no momento da conferência"
    try:
        recusar_pedido(pedido, request.user, motivo)
        messages.info(
            request,
            f"{pedido.numero} recusado. O cliente recebeu sugestões e a opção de estorno.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(request.META.get("HTTP_REFERER", "dashboard:painel"))


@operador_requerido
@require_POST
def enviar(request, numero):
    pedido = get_object_or_404(Pedido, numero=numero)
    try:
        marcar_enviado(pedido, request.user, request.POST.get("rastreio", ""))
        messages.success(request, f"{pedido.numero} marcado como enviado.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(request.META.get("HTTP_REFERER", "dashboard:painel"))


@operador_requerido
def estoque(request):
    produtos = Produto.objects.select_related("categoria").order_by("estoque")
    if request.GET.get("critico") == "1":
        produtos = produtos.filter(estoque__lte=F("estoque_minimo"))
    return render(
        request,
        "dashboard/estoque.html",
        {"secao": "estoque", "produtos": produtos[:200], "metricas": _metricas()},
    )


@operador_requerido
@require_POST
def repor_estoque(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)
    quantidade = int(request.POST.get("quantidade", 0))
    if quantidade > 0:
        produto.repor_estoque(quantidade, motivo="Reposição manual pelo painel")
        messages.success(request, f"{quantidade} un adicionadas a {produto.nome}.")
    return redirect("dashboard:estoque")


@operador_requerido
def produtos(request):
    """Lista de produtos com edição rápida de estoque, preço e publicação."""
    qs = Produto.objects.select_related("categoria", "marca").prefetch_related("imagens")
    busca = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "")

    if busca:
        qs = qs.filter(nome__icontains=busca) | qs.filter(sku__icontains=busca)
    if filtro == "sem-imagem":
        qs = qs.filter(imagens__isnull=True)
    elif filtro == "despublicados":
        qs = qs.filter(publicado=False)
    elif filtro == "sem-estoque":
        qs = qs.filter(estoque__lte=0)

    return render(
        request,
        "dashboard/produtos.html",
        {
            "secao": "produtos",
            "produtos": qs.order_by("nome")[:300],
            "total": qs.count(),
            "busca": busca,
            "filtro": filtro,
            "sem_imagem": Produto.objects.filter(imagens__isnull=True).count(),
            "metricas": _metricas(),
        },
    )


@operador_requerido
@require_POST
def salvar_produto_rapido(request, produto_id):
    """Edição em linha: preço, estoque e publicação, sem sair da listagem."""
    produto = get_object_or_404(Produto, pk=produto_id)
    try:
        if (preco := request.POST.get("preco")) not in (None, ""):
            produto.preco = Decimal(preco.replace(",", "."))
        if (estoque := request.POST.get("estoque")) not in (None, ""):
            novo = int(estoque)
            if novo != produto.estoque:
                diferenca = novo - produto.estoque
                MovimentoEstoque.objects.create(
                    produto=produto,
                    tipo=MovimentoEstoque.Tipo.AJUSTE,
                    quantidade=diferenca,
                    motivo=f"Ajuste manual pelo painel ({request.user.primeiro_nome})",
                )
                produto.estoque = novo
        produto.publicado = request.POST.get("publicado") == "1"
        produto.save(update_fields=["preco", "estoque", "publicado", "atualizado_em"])
        messages.success(request, f"{produto.nome[:40]} atualizado.")
    except (InvalidOperation, ValueError):
        messages.error(request, "Preço ou estoque inválido.")
    return redirect(request.META.get("HTTP_REFERER", "dashboard:produtos"))


@operador_requerido
@require_POST
def limpar_catalogo_view(request):
    """Zona de risco: apaga produtos para o lojista recomeçar do zero."""
    from apps.catalog.management.commands.limpar_catalogo import limpar

    acao = request.POST.get("acao")
    confirmacao = (request.POST.get("confirmacao") or "").strip().upper()

    if confirmacao != "LIMPAR":
        messages.error(request, 'Digite LIMPAR no campo de confirmação para prosseguir.')
        return redirect("dashboard:configuracoes")

    acoes = {
        "sem-imagem": {"sem_imagem": True},
        "produtos": {"produtos": True},
        "tudo": {"tudo": True},
        "zerar-estoque": {"zerar_estoque": True},
    }
    if acao not in acoes:
        messages.error(request, "Ação de limpeza desconhecida.")
        return redirect("dashboard:configuracoes")

    resumo = limpar(**acoes[acao])
    partes = []
    if resumo["apagados"]:
        partes.append(f"{resumo['apagados']} produto(s) apagado(s)")
    if resumo["despublicados"]:
        partes.append(
            f"{resumo['despublicados']} despublicado(s) por estarem em pedidos "
            "(o histórico é preservado)"
        )
    if resumo["zerados"]:
        partes.append(f"{resumo['zerados']} com estoque zerado")
    if resumo["auxiliares"]:
        partes.append(f"{resumo['auxiliares']} categoria/marca/espécie órfã(s) removida(s)")

    messages.success(request, "Catálogo limpo: " + (", ".join(partes) or "nada a fazer") + ".")
    return redirect("dashboard:produtos")


@operador_requerido
def metricas(request):
    trinta_dias = timezone.now() - timedelta(days=30)
    return render(
        request,
        "dashboard/metricas.html",
        {
            "secao": "metricas",
            "metricas": _metricas(),
            "por_status": Pedido.objects.values("status").annotate(
                quantidade=Count("id"), total=Sum("total")
            ),
            "por_metodo": Pagamento.objects.filter(status=Pagamento.Status.PAGO)
            .values("metodo")
            .annotate(quantidade=Count("id"), total=Sum("valor")),
            "mais_vendidos": Produto.objects.filter(vendas__gt=0).order_by("-vendas")[:10],
            "receita_30d": Pedido.objects.faturados()
            .filter(pago_em__gte=trinta_dias)
            .aggregate(t=Sum("total"))["t"]
            or 0,
        },
    )


@operador_requerido
def assinaturas(request):
    return render(
        request,
        "dashboard/assinaturas.html",
        {
            "secao": "assinaturas",
            "assinaturas": Assinatura.objects.select_related("usuario", "produto")[:100],
            "metricas": _metricas(),
        },
    )


@operador_requerido
def configuracoes(request):
    """Atalho para a configuração da Stone."""
    return render(
        request,
        "dashboard/configuracoes.html",
        {
            "secao": "config",
            "provedores": ProvedorPagamento.objects.all(),
            "provedor": ProvedorPagamento.ativo_padrao(),
            "metricas": _metricas(),
        },
    )


@operador_requerido
@require_POST
def marcar_notificacoes_lidas(request):
    Notificacao.objects.filter(
        publico=Notificacao.Publico.LOJISTA, lida_em__isnull=True
    ).update(lida_em=timezone.now())
    return redirect(request.META.get("HTTP_REFERER", "dashboard:painel"))
