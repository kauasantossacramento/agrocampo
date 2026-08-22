"""Painel do lojista: fila de aprovação, métricas, estoque e assinaturas."""
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Avg, Count, F, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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

def operador_requerido(view):
    """Exige um operador da loja.

    Anonimo vai para o login. Ja autenticado sem permissao recebe um 403
    explicito — antes ele era devolvido para a tela de login que acabara de
    passar, o que parecia a pagina simplesmente nao carregar.
    """

    @wraps(view)
    def _wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            destino = f"{reverse('accounts:entrar')}?next={quote(request.get_full_path())}"
            return redirect(destino)
        if not request.user.e_operador:
            return render(request, "dashboard/sem_permissao.html", status=403)
        return view(request, *args, **kwargs)

    return _wrapper


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
        Pedido.objects.select_related("usuario")
        .prefetch_related("itens__produto", "itens__variacao", "eventos", "pagamentos"),
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
            "link_whatsapp": _whatsapp_do_pedido(pedido),
        },
    )


def _whatsapp_do_pedido(pedido) -> str:
    """Conversa com o cliente já com o assunto escrito.

    Vazio quando não há número ou o cliente não autorizou — a tela então
    oferece o e-mail em vez de um botão que não leva a lugar nenhum.
    """
    from urllib.parse import quote

    base = pedido.usuario.whatsapp_url
    if not base:
        return ""

    texto = (
        f"Olá, {pedido.usuario.primeiro_nome}! Aqui é da AgroCampo, "
        f"sobre o seu pedido {pedido.numero}."
    )
    if pedido.itens_em_falta:
        texto += (
            f" Infelizmente ficou faltando: {pedido.itens_em_falta}. "
            "Podemos trocar por outro item ou devolver o valor — o que prefere?"
        )
    return f"{base}?text={quote(texto)}"


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
    """Tudo que o lojista edita, sem passar pelo admin do Django."""
    from apps.core.models import SiteConfig

    from . import forms as formularios

    config = SiteConfig.load()
    provedor = ProvedorPagamento.ativo_padrao()
    return render(
        request,
        "dashboard/configuracoes.html",
        {
            "secao": "config",
            "aba": request.GET.get("aba", "aparencia"),
            "config": config,
            "form_aparencia": formularios.AparenciaForm(instance=config),
            "form_contato": formularios.ContatoForm(instance=config),
            "form_regras": formularios.RegrasForm(instance=config),
            "form_entrega": formularios.EntregaForm(instance=config),
            "form_vitrines": formularios.VitrinesForm(instance=config),
            "form_firebase": formularios.FirebaseForm(instance=config),
            "form_provedor": formularios.ProvedorPagamentoForm(instance=provedor),
            "provedores": ProvedorPagamento.objects.all(),
            "provedor": provedor,
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


# ═══════════════════════════════════════════════ produto: wizard em modal
@operador_requerido
def produto_form(request, produto_id=None):
    """Devolve o formulário do wizard (fragmento carregado dentro do modal)."""
    from .forms import ProdutoForm

    produto = get_object_or_404(Produto, pk=produto_id) if produto_id else None
    return render(
        request,
        "dashboard/_produto_form.html",
        _contexto_wizard(ProdutoForm(instance=produto), produto),
    )


def _contexto_wizard(form, produto):
    from apps.catalog.models import VariacaoProduto

    return {
        "form": form,
        "produto": produto,
        "variacoes": (produto.variacoes.order_by("ordem", "preco") if produto else []),
        "unidades_variacao": VariacaoProduto.Unidade.choices,
    }


def _salvar_variacoes(request, produto):
    """Grava os tamanhos vindos do wizard.

    As linhas chegam indexadas (`var-0-preco`, `var-1-preco`…) porque o índice
    é o que amarra o arquivo de imagem à linha certa. Linhas sem quantidade ou
    sem preço são descartadas em silêncio — no celular é fácil tocar em
    "adicionar" sem querer.
    """
    from decimal import Decimal, InvalidOperation
    import re

    from apps.catalog.models import VariacaoProduto

    indices = sorted(
        {int(m.group(1)) for chave in request.POST
         if (m := re.fullmatch(r"var-(\d+)-quantidade", chave))}
    )
    padrao = request.POST.get("var_padrao", "")
    mantidos = []

    for ordem, i in enumerate(indices):
        def campo(nome, vazio=""):
            return (request.POST.get(f"var-{i}-{nome}") or vazio).strip()

        try:
            quantidade = Decimal(campo("quantidade").replace(",", "."))
            preco = Decimal(campo("preco").replace(",", "."))
        except (InvalidOperation, ValueError):
            continue
        if quantidade <= 0 or preco <= 0:
            continue

        try:
            promocional = Decimal(campo("preco_promocional").replace(",", "."))
        except (InvalidOperation, ValueError):
            promocional = None
        if promocional is not None and promocional >= preco:
            promocional = None   # promoção maior que o preço não é promoção

        dados = {
            "quantidade": quantidade,
            "unidade": campo("unidade", "kg"),
            "preco": preco,
            "preco_promocional": promocional,
            "estoque": int(campo("estoque", "0") or 0),
            "padrao": str(i) == padrao,
            "ordem": ordem,
            "ativo": True,
        }

        existente_id = campo("id")
        variacao = None
        if existente_id:
            variacao = produto.variacoes.filter(pk=existente_id).first()
        if variacao:
            for atributo, valor in dados.items():
                setattr(variacao, atributo, valor)
        else:
            variacao = VariacaoProduto(produto=produto, **dados)

        imagem = request.FILES.get(f"var-{i}-imagem")
        if imagem:
            variacao.imagem = imagem
        variacao.save()
        mantidos.append(variacao.pk)

    # o que sumiu da tela sai do banco
    produto.variacoes.exclude(pk__in=mantidos).delete()

    # sem nenhuma marcada, a primeira vira a padrão: a vitrine precisa
    # de um preço para mostrar
    if mantidos and not produto.variacoes.filter(padrao=True).exists():
        produto.variacoes.filter(pk=mantidos[0]).update(padrao=True)


@operador_requerido
@require_POST
def produto_salvar(request, produto_id=None):
    """Salva o wizard. Responde JSON — o modal não recarrega a página."""
    from django.template.loader import render_to_string

    from apps.catalog.models import ProdutoImagem

    from .forms import ProdutoForm

    produto = get_object_or_404(Produto, pk=produto_id) if produto_id else None
    form = ProdutoForm(request.POST, instance=produto)

    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "erros": {c: [str(e) for e in erros] for c, erros in form.errors.items()},
                "html": render_to_string(
                    "dashboard/_produto_form.html",
                    _contexto_wizard(form, produto),
                    request=request,
                ),
            },
            status=400,
        )

    produto = form.save()

    # fotos vêm no mesmo POST — câmera do celular ou galeria
    for arquivo in request.FILES.getlist("fotos"):
        ProdutoImagem.objects.create(produto=produto, imagem=arquivo)

    remover = request.POST.getlist("remover_imagem")
    if remover:
        ProdutoImagem.objects.filter(produto=produto, pk__in=remover).delete()

    _salvar_variacoes(request, produto)

    return JsonResponse({
        "ok": True,
        "id": produto.pk,
        "nome": produto.nome,
        "criado": produto_id is None,
        "url": produto.get_absolute_url(),
    })


@operador_requerido
@require_POST
def produto_remover_foto(request, imagem_id):
    from apps.catalog.models import ProdutoImagem

    ProdutoImagem.objects.filter(pk=imagem_id).delete()
    return JsonResponse({"ok": True})


# ═══════════════════════════════════════════════ configurações por seção
SECOES_CONFIG = {
    "aparencia": ("AparenciaForm", "Aparência da loja"),
    "contato": ("ContatoForm", "Contato e rodapé"),
    "regras": ("RegrasForm", "Regras da loja"),
    "entrega": ("EntregaForm", "Entrega e WhatsApp"),
    "vitrines": ("VitrinesForm", "Vitrines da home"),
    "firebase": ("FirebaseForm", "Notificações push"),
}


@operador_requerido
@require_POST
def salvar_config(request, secao):
    """Salva uma seção da configuração da loja."""
    from apps.core.models import SiteConfig

    from . import forms as formularios

    if secao not in SECOES_CONFIG:
        messages.error(request, "Seção desconhecida.")
        return redirect("dashboard:configuracoes")

    nome_form, rotulo = SECOES_CONFIG[secao]
    form = getattr(formularios, nome_form)(
        request.POST, request.FILES, instance=SiteConfig.load()
    )

    if form.is_valid():
        form.save()
        messages.success(request, f"{rotulo} atualizada.")
    else:
        for campo, erros in form.errors.items():
            prefixo = "" if campo == "__all__" else f"{form.fields[campo].label}: "
            messages.error(request, f"{prefixo}{' '.join(erros)}")

    return redirect(f"{reverse('dashboard:configuracoes')}?aba={secao}")


@operador_requerido
@require_POST
def salvar_provedor(request, provedor_id):
    """Credenciais da Stone e regras de cobrança, direto no painel."""
    from .forms import ProvedorPagamentoForm

    provedor = get_object_or_404(ProvedorPagamento, pk=provedor_id)
    form = ProvedorPagamentoForm(request.POST, instance=provedor)

    if form.is_valid():
        form.save()
        messages.success(request, "Provedor de pagamento atualizado.")
    else:
        for campo, erros in form.errors.items():
            prefixo = "" if campo == "__all__" else f"{form.fields[campo].label}: "
            messages.error(request, f"{prefixo}{' '.join(erros)}")

    return redirect(f"{reverse('dashboard:configuracoes')}?aba=pagamentos")


# ═══════════════════════════════════ conteúdo da loja (telas nativas)
def _secao_ou_404(slug):
    from django.http import Http404

    from .gestao import SECOES

    if slug not in SECOES:
        raise Http404("Seção desconhecida.")
    return SECOES[slug]


@operador_requerido
def gestao(request, slug):
    """Listagem genérica de uma seção de conteúdo."""
    from django.db.models import Q

    from .gestao import secoes_agrupadas

    secao = _secao_ou_404(slug)
    qs = secao.queryset()

    busca = request.GET.get("q", "").strip()
    if busca and secao.busca:
        filtro = Q()
        for campo in secao.busca:
            filtro |= Q(**{f"{campo}__icontains": busca})
        qs = qs.filter(filtro)

    # pares (rótulo, valor): o template não faz aritmética de índice.
    # Com `slice:forloop.counter0` os rótulos saíam deslocados uma coluna —
    # slice:"0" devolve lista vazia.
    linhas = [
        {"obj": obj, "celulas": [(rotulo, funcao(obj)) for rotulo, funcao in secao.colunas]}
        for obj in qs[:300]
    ]

    return render(
        request,
        "dashboard/gestao.html",
        {
            "secao_atual": secao,
            "grupos": secoes_agrupadas().items(),
            "colunas": [c[0] for c in secao.colunas],
            "linhas": linhas,
            "total": qs.count(),
            "busca": busca,
            # a barra lateral acende "Entrega" para cidades/localidades/avisos
            "secao": "entrega" if secao.grupo == "Entrega" else "conteudo",
            "metricas": _metricas(),
        },
    )


@operador_requerido
def gestao_form(request, slug, pk=None):
    """Fragmento do formulário, carregado no modal."""
    secao = _secao_ou_404(slug)
    obj = get_object_or_404(secao.model, pk=pk) if pk else None
    return render(
        request,
        "dashboard/_gestao_form.html",
        {"form": secao.form(instance=obj), "secao_atual": secao, "obj": obj},
    )


@operador_requerido
@require_POST
def gestao_salvar(request, slug, pk=None):
    from django.template.loader import render_to_string

    secao = _secao_ou_404(slug)
    obj = get_object_or_404(secao.model, pk=pk) if pk else None
    form = secao.form(request.POST, request.FILES, instance=obj)

    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "erros": {c: [str(e) for e in erros] for c, erros in form.errors.items()},
                "html": render_to_string(
                    "dashboard/_gestao_form.html",
                    {"form": form, "secao_atual": secao, "obj": obj},
                    request=request,
                ),
            },
            status=400,
        )

    salvo = form.save()
    return JsonResponse({"ok": True, "id": salvo.pk, "criado": pk is None})


@operador_requerido
@require_POST
def gestao_excluir(request, slug, pk):
    from django.db.models import ProtectedError

    secao = _secao_ou_404(slug)
    obj = get_object_or_404(secao.model, pk=pk)
    rotulo = str(obj)

    try:
        obj.delete()
        messages.success(request, f"{rotulo} removido.")
    except ProtectedError:
        # o registro está em uso; apagar quebraria histórico
        messages.error(
            request,
            f"{rotulo} está em uso e não pode ser apagado. "
            "Desmarque “no ar” para tirá-lo do site sem perder o histórico.",
        )
    return redirect("dashboard:gestao", slug=slug)


# ═══════════════════════════════════════════ auditoria de pagamentos
AUDITORIA = {
    "pagamentos": {
        "titulo": "Pagamentos",
        "descricao": "Cada cobrança enviada ao adquirente.",
        "colunas": ["Pedido", "Método", "Valor", "Status", "ID na Stone", "Quando"],
    },
    "webhooks": {
        "titulo": "Eventos de webhook",
        "descricao": "Notificações recebidas da Stone, na ordem em que chegaram.",
        "colunas": ["Tipo", "Referência", "Assinatura", "Processado", "Quando"],
    },
    "estornos": {
        "titulo": "Estornos",
        "descricao": "Devoluções solicitadas e o desfecho de cada uma.",
        "colunas": ["Pedido", "Valor", "Motivo", "Status", "Quando"],
    },
    "transacoes": {
        "titulo": "Transações com a Stone",
        "descricao": "Trilha bruta: cada chamada, com duração e resposta.",
        "colunas": ["Pedido", "Operação", "Resultado", "HTTP", "Duração", "Quando"],
    },
}


@operador_requerido
def auditoria(request, tipo):
    """Listagens somente leitura do rastro de pagamentos."""
    from django.http import Http404

    from apps.payments.models import (
        Estorno,
        EventoWebhook,
        Pagamento,
        TransacaoPagamento,
    )

    if tipo not in AUDITORIA:
        raise Http404("Seção desconhecida.")

    busca = request.GET.get("q", "").strip()

    if tipo == "pagamentos":
        qs = Pagamento.objects.select_related("pedido")
        if busca:
            qs = qs.filter(pedido__numero__icontains=busca) | qs.filter(
                referencia_externa__icontains=busca
            )
        colunas = AUDITORIA[tipo]["colunas"]
        linhas = [
            {
                "obj": p,
                "celulas": list(zip(colunas, [
                    p.pedido.numero, p.get_metodo_display(), f"R$ {p.valor:.2f}",
                    p.get_status_display(), p.referencia_externa or "—", p.criado_em,
                ])),
            }
            for p in qs[:200]
        ]
    elif tipo == "webhooks":
        qs = EventoWebhook.objects.all()
        if busca:
            qs = qs.filter(referencia_externa__icontains=busca)
        colunas = AUDITORIA[tipo]["colunas"]
        linhas = [
            {
                "obj": e,
                "celulas": list(zip(colunas, [
                    e.tipo or "—", e.referencia_externa or "—",
                    "válida" if e.assinatura_valida else "INVÁLIDA",
                    "sim" if e.processado else "pendente", e.criado_em,
                ])),
            }
            for e in qs[:200]
        ]
    elif tipo == "estornos":
        qs = Estorno.objects.select_related("pagamento__pedido")
        colunas = AUDITORIA[tipo]["colunas"]
        linhas = [
            {
                "obj": x,
                "celulas": list(zip(colunas, [
                    x.pagamento.pedido.numero, f"R$ {x.valor:.2f}",
                    x.get_motivo_display(), x.get_status_display(), x.criado_em,
                ])),
            }
            for x in qs[:200]
        ]
    else:
        qs = TransacaoPagamento.objects.select_related("pagamento__pedido")
        colunas = AUDITORIA[tipo]["colunas"]
        linhas = [
            {
                "obj": t,
                "celulas": list(zip(colunas, [
                    t.pagamento.pedido.numero, t.get_operacao_display(),
                    "sucesso" if t.sucesso else "falha", t.http_status or "—",
                    f"{t.duracao_ms} ms" if t.duracao_ms else "—", t.criado_em,
                ])),
            }
            for t in qs[:200]
        ]

    return render(
        request,
        "dashboard/auditoria.html",
        {
            "tipo": tipo,
            "info": AUDITORIA[tipo],
            "abas": AUDITORIA,
            "linhas": linhas,
            "total": qs.count(),
            "busca": busca,
            "secao": "auditoria",
            "metricas": _metricas(),
        },
    )
