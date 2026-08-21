"""Vitrine: catálogo com filtros facetados, produto, categoria, marca e espécie."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Max, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Avaliacao, Categoria, Especie, ListaDesejos, Marca, Produto

ORDENACOES = {
    "relevancia": ("-destaque", "-vendas", "-criado_em"),
    "menor-preco": ("preco",),
    "maior-preco": ("-preco",),
    "novidades": ("-criado_em",),
    "mais-vendidos": ("-vendas",),
    "avaliacao": ("-nota_media",),
}


def _decimal(valor):
    try:
        return Decimal(valor)
    except (TypeError, InvalidOperation):
        return None


def catalogo(request, categoria=None, marca=None, especie=None):
    """Listagem única que atende /catalogo, /categoria/, /marca/ e /especie/."""
    produtos = Produto.objects.vitrine()
    titulo = "Catálogo"
    contexto_extra = {}

    if categoria:
        produtos = produtos.filter(categoria_id__in=categoria.ramo_ids)
        titulo = categoria.nome
        contexto_extra["categoria_atual"] = categoria
    if marca:
        produtos = produtos.filter(marca=marca)
        titulo = marca.nome
        contexto_extra["marca_atual"] = marca
    if especie:
        produtos = produtos.filter(especies=especie)
        titulo = f"Para {especie.nome}"
        contexto_extra["especie_atual"] = especie

    busca = request.GET.get("q", "").strip()
    if busca:
        produtos = produtos.filter(
            Q(nome__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(resumo__icontains=busca)
            | Q(sku__icontains=busca)
            | Q(categoria__nome__icontains=busca)
            | Q(marca__nome__icontains=busca)
        ).distinct()

    faixa = produtos.aggregate(minimo=Min("preco"), maximo=Max("preco"))
    preco_min = _decimal(request.GET.get("preco_min"))
    preco_max = _decimal(request.GET.get("preco_max"))
    if preco_min is not None:
        produtos = produtos.filter(preco__gte=preco_min)
    if preco_max is not None:
        produtos = produtos.filter(preco__lte=preco_max)

    marcas_filtro = request.GET.getlist("marca")
    if marcas_filtro:
        produtos = produtos.filter(marca__slug__in=marcas_filtro)

    if request.GET.get("assinatura") == "1":
        produtos = produtos.filter(permite_assinatura=True)
    if request.GET.get("promocao") == "1":
        produtos = produtos.filter(preco_promocional__isnull=False)
    if request.GET.get("disponivel") == "1":
        produtos = produtos.filter(estoque__gt=0)

    ordem = request.GET.get("ordem", "relevancia")
    produtos = produtos.order_by(*ORDENACOES.get(ordem, ORDENACOES["relevancia"]))

    paginator = Paginator(produtos, 24)
    pagina = paginator.get_page(request.GET.get("pagina"))

    # querystring sem o parâmetro de página, para os links do paginador
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(
        request,
        "catalog/catalogo.html",
        {
            "titulo": titulo,
            "pagina": pagina,
            "produtos": pagina.object_list,
            "total": paginator.count,
            "busca": busca,
            "ordem": ordem,
            "ordenacoes": ORDENACOES.keys(),
            "categorias": Categoria.objects.menu(),
            "marcas": Marca.objects.publicados(),
            "marcas_selecionadas": marcas_filtro,
            "faixa": faixa,
            "preco_min": preco_min,
            "preco_max": preco_max,
            "querystring": parametros.urlencode(),
            **contexto_extra,
        },
    )


def por_categoria(request, slug):
    categoria = get_object_or_404(
        Categoria.objects.publicados().prefetch_related("filhas"), slug=slug
    )
    return catalogo(request, categoria=categoria)


def por_marca(request, slug):
    return catalogo(request, marca=get_object_or_404(Marca.objects.publicados(), slug=slug))


def por_especie(request, slug):
    return catalogo(
        request, especie=get_object_or_404(Especie.objects.publicados(), slug=slug)
    )


def detalhe_produto(request, slug):
    produto = get_object_or_404(
        Produto.objects.vitrine().prefetch_related("especies", "avaliacoes__autor"),
        slug=slug,
    )
    avaliacoes = produto.avaliacoes.filter(aprovada=True).select_related("autor")[:10]
    ja_avaliou = (
        request.user.is_authenticated
        and produto.avaliacoes.filter(autor=request.user).exists()
    )
    return render(
        request,
        "catalog/produto.html",
        {
            "produto": produto,
            "avaliacoes": avaliacoes,
            "ja_avaliou": ja_avaliou,
            "relacionados": produto.similares(4),
            "frequencias": [(30, "30 dias"), (60, "60 dias"), (90, "90 dias")],
        },
    )


def marcas(request):
    return render(
        request,
        "catalog/marcas.html",
        {"marcas": Marca.objects.publicados().order_by("nome")},
    )


def especies(request):
    grupos = []
    for valor, rotulo in Especie.Grupo.choices:
        itens = Especie.objects.publicados().filter(grupo=valor)
        if itens:
            grupos.append({"nome": rotulo, "itens": itens})
    return render(
        request,
        "catalog/especies.html",
        {
            "grupos": grupos,
            # CC-BY exige atribuição: a lista completa fica ao pé da página
            "creditos": Especie.objects.publicados().exclude(credito_imagem="").order_by("nome"),
        },
    )


@require_POST
@login_required
def avaliar(request, slug):
    produto = get_object_or_404(Produto, slug=slug)
    nota = int(request.POST.get("nota", 5))
    Avaliacao.objects.update_or_create(
        produto=produto,
        autor=request.user,
        defaults={
            "nota": max(1, min(5, nota)),
            "titulo": request.POST.get("titulo", "")[:120],
            "comentario": request.POST.get("comentario", ""),
        },
    )
    messages.success(request, "Obrigado pela avaliação!")
    return redirect(produto.get_absolute_url())


@require_POST
@login_required
def alternar_desejo(request, slug):
    produto = get_object_or_404(Produto, slug=slug)
    desejo = ListaDesejos.objects.filter(usuario=request.user, produto=produto).first()
    if desejo:
        desejo.delete()
        messages.info(request, f"{produto.nome} saiu da sua lista de desejos.")
    else:
        ListaDesejos.objects.create(usuario=request.user, produto=produto)
        messages.success(request, f"{produto.nome} salvo na lista de desejos.")
    return redirect(request.META.get("HTTP_REFERER", produto.get_absolute_url()))
