"""Vitrine: catálogo com filtros facetados, produto, categoria, marca e espécie."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Max, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.shipping.models import Cidade

from .models import LinhaProduto, Avaliacao, Categoria, Especie, ListaDesejos, Marca, Produto

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


def _sem_acento(texto: str) -> str:
    """Tira acento e caixa: "Cão" e "cao" passam a ser a mesma coisa."""
    import unicodedata

    normalizado = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn").lower().strip()


def _especies_por_apelido(termo: str):
    """Espécies cujo nome ou apelido contém o termo digitado.

    A comparação é em Python de propósito: são poucas dezenas de espécies, e
    assim funciona igual no SQLite do desenvolvimento e no Postgres do
    servidor, sem depender da extensão `unaccent`.
    """
    alvo = _sem_acento(termo)
    if len(alvo) < 2:
        return []

    achadas = []
    for especie in Especie.objects.all().only("id", "nome", "sinonimos"):
        if any(alvo in _sem_acento(apelido) for apelido in especie.apelidos):
            achadas.append(especie.pk)
            # quem procura "cachorro" quer a família toda, não só a mãe
            achadas.extend(especie.agrupadas.values_list("pk", flat=True))
    return achadas


PALAVRAS_SEM_PESO = {
    "para", "pra", "de", "da", "do", "das", "dos", "com", "sem", "e", "em",
    "no", "na", "nos", "nas", "a", "o", "as", "os", "um", "uma", "meu", "minha",
}


def _condicao_de_busca(busca: str):
    """Monta o filtro da busca a partir da frase digitada.

    Cada palavra precisa aparecer em algum lugar do produto — assim "ração
    para cachorro" acha a ração de cão, em vez de procurar a frase inteira
    dentro de um nome que nunca a contém. Palavras de ligação são ignoradas:
    exigir "para" só tiraria resultado bom da frente do cliente.
    """
    palavras = [
        p for p in _sem_acento(busca).split()
        if len(p) >= 2 and p not in PALAVRAS_SEM_PESO
    ] or [_sem_acento(busca)]

    condicao = Q()
    for palavra in palavras:
        especies = _especies_por_apelido(palavra)
        desta_palavra = (
            Q(busca_normalizada__icontains=palavra)
            | Q(categoria__nome__icontains=palavra)
            | Q(marca__nome__icontains=palavra)
            | Q(especies__nome__icontains=palavra)
        )
        if especies:
            # "cachorro" não aparece no cadastro — a espécie se chama "Cão"
            desta_palavra |= Q(especies__in=especies)
        condicao &= desta_palavra
    return condicao


def _produtos_em_destaque(busca: str):
    """ids dos produtos que o lojista mandou mostrar primeiro para esta busca."""
    from apps.catalog.models import DestaqueBusca

    ids = []
    for destaque in DestaqueBusca.objects.filter(ativo=True).prefetch_related("produtos"):
        if destaque.atende(busca):
            ids.extend(destaque.produtos_alvo().values_list("pk", flat=True))
    return ids


def catalogo(request, categoria=None, marca=None, especie=None):
    """Listagem única que atende /catalogo, /categoria/, /marca/ e /especie/."""
    produtos = Produto.objects.vitrine()
    titulo = "Catálogo"
    contexto_extra = {}

    if request.GET.get("banner"):
        from apps.core.models import Banner

        identificador = request.GET["banner"]
        if not identificador.isascii() or not identificador.isdigit() or len(identificador) > 10:
            from django.http import Http404
            raise Http404
        banner = get_object_or_404(Banner.objects.publicados(), pk=int(identificador), tipo_destino=Banner.TipoDestino.PRODUTOS)
        produtos = produtos.filter(banners=banner)
        titulo = banner.titulo or "Seleção de produtos"

    if categoria:
        produtos = produtos.filter(categoria_id__in=categoria.ramo_ids)
        titulo = categoria.nome
        contexto_extra["categoria_atual"] = categoria
    if marca:
        produtos = produtos.filter(marca=marca)
        titulo = marca.nome
        contexto_extra["marca_atual"] = marca
    if especie:
        # a espécie-mãe traz junto o que está agrupado nela
        produtos = produtos.filter(especies__in=especie.familia_ids).distinct()
        titulo = f"Para {especie.nome}"
        contexto_extra["especie_atual"] = especie

    busca = request.GET.get("q", "").strip()
    destacados = []
    if busca:
        produtos = produtos.filter(_condicao_de_busca(busca)).distinct()
        destacados = _produtos_em_destaque(busca)

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

    linha = request.GET.get("linha", "")
    if linha and LinhaProduto.objects.filter(slug=linha, ativo=True).exists():
        produtos = produtos.da_linha(linha)
        titulo = LinhaProduto.objects.get(slug=linha).nome

    if request.GET.get("assinatura") == "1":
        produtos = produtos.filter(permite_assinatura=True)
    if request.GET.get("promocao") == "1":
        produtos = produtos.filter(preco_promocional__isnull=False)
    if request.GET.get("disponivel") == "1":
        # sob encomenda também está disponível: o filtro escondia a loja inteira
        produtos = produtos.filter(Q(estoque__gt=0) | Q(sem_controle_estoque=True))

    ordem = request.GET.get("ordem", "relevancia")
    produtos = produtos.order_by(*ORDENACOES.get(ordem, ORDENACOES["relevancia"]))

    # Os destaques só mandam na relevância: quem pediu "menor preço" quer
    # menor preço, e furar essa fila seria enganar o cliente.
    if destacados and ordem == "relevancia":
        from django.db.models import Case, IntegerField, Value, When

        produtos = produtos.annotate(
            _destaque=Case(
                When(pk__in=destacados, then=Value(0)),
                default=Value(1), output_field=IntegerField(),
            )
        ).order_by("_destaque", *ORDENACOES["relevancia"])

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
            # usado no estado vazio: "o catálogo tem N produtos esperando por você"
            "total_catalogo": Produto.objects.publicados().count(),
            "busca": busca,
            "ordem": ordem,
            "ordenacoes": ORDENACOES.keys(),
            "linhas": [(l.slug, l.nome) for l in LinhaProduto.objects.filter(ativo=True)],
            "linha_atual": linha,
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
    especie = get_object_or_404(Especie.objects.publicados(), slug=slug)
    # link antigo de pássaro específico continua valendo: leva para o card
    # que agora o representa, sem deixar ninguém numa página vazia
    if especie.agrupada_em_id and especie.agrupada_em.publicado:
        return redirect(especie.agrupada_em.get_absolute_url(), permanent=True)
    return catalogo(request, especie=especie)


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
    pode_avaliar = produto.foi_comprado_por(request.user)
    return render(
        request,
        "catalog/produto.html",
        {
            "mostrar_assistente": True,
            "cidades_frete": Cidade.objects.atendidas().prefetch_related("localidades"),
            "produto": produto,
            "avaliacoes": avaliacoes,
            "ja_avaliou": ja_avaliou,
            "pode_avaliar": pode_avaliar,
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
        itens = Especie.objects.navegaveis().filter(grupo=valor)
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

    # A checagem vive aqui, no servidor: esconder o formulário no template
    # não impede um POST direto.
    if not produto.foi_comprado_por(request.user):
        messages.error(
            request,
            "Só quem comprou este produto pode avaliá-lo. "
            "A avaliação libera assim que o pedido for aprovado.",
        )
        return redirect(produto.get_absolute_url())

    nota = int(request.POST.get("nota", 5))
    Avaliacao.objects.update_or_create(
        produto=produto,
        autor=request.user,
        defaults={
            "nota": max(1, min(5, nota)),
            "titulo": request.POST.get("titulo", "")[:120],
            "comentario": request.POST.get("comentario", ""),
            "compra_verificada": True,
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


def sugestoes(request):
    """Sugestões da busca enquanto a pessoa digita (JSON).

    Com termo: categorias, marcas, espécies e produtos que batem. Sem termo:
    "buscas populares" — categorias e espécies em destaque — para a caixa não
    abrir vazia.
    """
    from django.db.models import Q
    from django.http import JsonResponse

    termo = (request.GET.get("q") or "").strip()[:60]
    grupos = []

    if len(termo) < 2:
        populares = [
            {"rotulo": c.nome, "url": c.get_absolute_url(), "icone": "pacote"}
            for c in Categoria.objects.publicados().filter(destaque_home=True)[:4]
        ] + [
            {"rotulo": e.nome, "url": e.get_absolute_url(), "icone": "folha"}
            for e in Especie.objects.publicados().filter(destaque_home=True)[:4]
        ]
        if populares:
            grupos.append({"titulo": "Buscas populares", "itens": populares})
        return JsonResponse({"grupos": grupos, "termo": termo})

    atalhos = []
    for c in Categoria.objects.publicados().filter(nome__icontains=termo)[:3]:
        atalhos.append({"rotulo": c.nome, "url": c.get_absolute_url(), "icone": "pacote",
                        "extra": f"{c.produtos.filter(publicado=True).count()} produtos"})
    for m in Marca.objects.publicados().filter(nome__icontains=termo)[:2]:
        atalhos.append({"rotulo": m.nome, "url": m.get_absolute_url(), "icone": "medalha", "extra": "marca"})
    # a espécie também entra pelo apelido: quem digita "cachorro" vê o atalho
    # de Cão, que é como ela está cadastrada
    achadas = _especies_por_apelido(termo)
    for e in Especie.objects.navegaveis().filter(
        Q(nome__icontains=termo) | Q(pk__in=achadas)
    )[:2]:
        atalhos.append({"rotulo": e.nome, "url": e.get_absolute_url(), "icone": "folha", "extra": "espécie"})
    if atalhos:
        grupos.append({"titulo": "Categorias, marcas e espécies", "itens": atalhos})

    condicao = (
        Q(busca_normalizada__icontains=_sem_acento(termo))
        | Q(nome__icontains=termo)
        | Q(sku__iexact=termo)
        | Q(marca__nome__icontains=termo)
    )
    if achadas:
        condicao |= Q(especies__in=achadas)

    produtos = (
        Produto.objects.vitrine()
        .filter(condicao)
        .distinct()
        .select_related("marca")
        .prefetch_related("imagens")
        .order_by("-vendas", "nome")[:6]
    )
    itens = []
    for p in produtos:
        foto = p.foto_principal
        itens.append({
            "rotulo": p.nome,
            "url": p.get_absolute_url(),
            "extra": p.marca.nome if p.marca else "",
            "preco": f"R$ {p.preco_atual:.2f}".replace(".", ","),
            "a_partir": p.tem_variacoes,
            "foto": foto.url if foto else "",
        })
    if itens:
        grupos.append({"titulo": "Produtos", "itens": itens, "produtos": True})

    return JsonResponse({
        "grupos": grupos, "termo": termo,
        "ver_todos": f"/busca/?q={termo}",
    })
