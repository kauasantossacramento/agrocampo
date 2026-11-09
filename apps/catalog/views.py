"""Vitrine: catálogo com filtros facetados, produto, categoria, marca e espécie."""
import re
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


# Uma palavra da busca casa com o começo de uma palavra do cadastro, nunca
# com o meio. Pelo meio, "cão" casava com "raÇÃO" e "alimentaÇÃO": buscar
# "cão" trazia toda ração da loja, inclusive a de gato, e "cão" e "cachorro"
# davam resultados diferentes. O padrão é o mesmo no Postgres e no SQLite.
INICIO_DE_PALAVRA = r"(^|[^a-z0-9])"
FIM_DE_PALAVRA = r"([^a-z0-9]|$)"


def _palavras(texto: str) -> list[str]:
    """Quebra em palavras já sem acento: "anti-pulgas" vira anti e pulgas."""
    return re.findall(r"[a-z0-9]+", _sem_acento(texto))


def _regex_no_inicio(forma: str, inteira: bool = False) -> str:
    return INICIO_DE_PALAVRA + re.escape(forma) + (FIM_DE_PALAVRA if inteira else "")


def _casa_no_inicio(texto: str, forma: str, inteira: bool = False) -> bool:
    return re.search(_regex_no_inicio(forma, inteira), _sem_acento(texto)) is not None


def _por_nome_sem_acento(modelo, termo: str, inteira: bool = False):
    """pks do modelo cujo nome tem uma palavra que começa pelo termo.

    O `icontains` do banco compara acento: "racao" não casa com a categoria
    "Ração". São poucas dezenas de categorias e marcas, então a comparação
    sai em Python e funciona igual no SQLite e no Postgres.
    """
    alvo = _sem_acento(termo)
    if len(alvo) < 2:
        return []
    return [
        pk for pk, nome in modelo.objects.values_list("pk", "nome")
        if _casa_no_inicio(nome, alvo, inteira)
    ]


def _especies_por_apelido(termo: str, inteira: bool = False):
    """Espécies cujo nome ou apelido começa pelo termo digitado.

    A comparação é em Python de propósito: são poucas dezenas de espécies, e
    assim funciona igual no SQLite do desenvolvimento e no Postgres do
    servidor, sem depender da extensão `unaccent`.
    """
    alvo = _sem_acento(termo)
    if len(alvo) < 2:
        return []

    achadas = []
    for especie in Especie.objects.all().only("id", "nome", "sinonimos"):
        if any(_casa_no_inicio(apelido, alvo, inteira) for apelido in especie.apelidos):
            achadas.append(especie.pk)
            # quem procura "cachorro" quer a família toda, não só a mãe
            achadas.extend(especie.agrupadas.values_list("pk", flat=True))
    return achadas


PALAVRAS_SEM_PESO = {
    "para", "pra", "de", "da", "do", "das", "dos", "com", "sem", "e", "em",
    "no", "na", "nos", "nas", "a", "o", "as", "os", "um", "uma", "meu", "minha",
}


def _palavras_da_busca(busca: str) -> list[str]:
    """As palavras que valem na busca, já sem acento e sem as de ligação."""
    palavras = [
        p for p in _palavras(busca)
        if len(p) >= 2 and p not in PALAVRAS_SEM_PESO
    ]
    return palavras or _palavras(busca)[:1]


def _formas(palavra: str) -> dict[str, bool]:
    """Tudo o que esta palavra pode querer dizer: {forma: só palavra inteira?}.

    - o que foi digitado vale pelo começo ("cach" já acha "cachorro");
    - o singular e os sinônimos do grupo entram também;
    - forma derivada curta ("ave", "boi") só vale como palavra inteira:
      pelo começo, "ave" traria a aveia.

    Quem ainda está digitando ("cachor") já ganha o grupo do sinônimo que a
    palavra começa — é o que faz a prévia acertar antes do fim da palavra.
    """
    from apps.catalog.models import SinonimoBusca, singular

    formas = {palavra: False}
    derivadas = {singular(palavra)}
    raiz = singular(palavra)
    for grupo in SinonimoBusca.grupos():
        no_grupo = palavra in grupo or any(singular(t) == raiz for t in grupo)
        comeco = len(palavra) >= 4 and any(t.startswith(palavra) for t in grupo)
        if no_grupo or comeco:
            derivadas |= grupo
            derivadas |= {singular(t) for t in grupo}
    for forma in derivadas:
        if forma and forma not in formas:
            formas[forma] = len(forma) <= 3
    return formas


def _condicao_de_busca(busca: str):
    """Monta o filtro da busca a partir da frase digitada.

    Cada palavra precisa aparecer em algum lugar do produto — assim "ração
    para cachorro" acha a ração de cão, em vez de procurar a frase inteira
    dentro de um nome que nunca a contém. Palavras de ligação são ignoradas:
    exigir "para" só tiraria resultado bom da frente do cliente.
    """
    condicao = Q()
    for palavra in _palavras_da_busca(busca):
        desta_palavra = Q()
        for forma, inteira in _formas(palavra).items():
            desta_palavra |= Q(busca_normalizada__iregex=_regex_no_inicio(forma, inteira))
            categorias = _por_nome_sem_acento(Categoria, forma, inteira)
            if categorias:
                desta_palavra |= Q(categoria__in=categorias)
            marcas = _por_nome_sem_acento(Marca, forma, inteira)
            if marcas:
                desta_palavra |= Q(marca__in=marcas)
            especies = _especies_por_apelido(forma, inteira)
            if especies:
                # "cachorro" não aparece no cadastro — a espécie se chama "Cão"
                desta_palavra |= Q(especies__in=especies)
        condicao &= desta_palavra
    return condicao


def _condicao_no_nome(busca: str):
    """Só o que bate no nome do produto — serve para ordenar, não para filtrar."""
    condicao = Q()
    for palavra in _palavras_da_busca(busca):
        desta_palavra = Q()
        for forma, inteira in _formas(palavra).items():
            desta_palavra |= Q(nome_normalizado__iregex=_regex_no_inicio(forma, inteira))
        condicao &= desta_palavra
    return condicao


def _vocabulario() -> set[str]:
    """Todas as palavras que a loja conhece, para corrigir erro de digitação.

    Nomes de produto, categorias, marcas, espécies e sinônimos. Guardado dez
    minutos: muda quando o lojista cadastra, não a cada busca.
    """
    from django.core.cache import cache

    from apps.catalog.models import SinonimoBusca

    vocabulario = cache.get("busca:vocabulario")
    if vocabulario is not None:
        return vocabulario

    textos = list(Produto.objects.vitrine().values_list("nome", flat=True))
    textos += list(Categoria.objects.values_list("nome", flat=True))
    textos += list(Marca.objects.values_list("nome", flat=True))
    for especie in Especie.objects.all().only("nome", "sinonimos"):
        textos += list(especie.apelidos)
    for grupo in SinonimoBusca.grupos():
        textos += list(grupo)

    vocabulario = {p for texto in textos for p in _palavras(texto) if len(p) >= 4 and not p.isdigit()}
    cache.set("busca:vocabulario", vocabulario, 600)
    return vocabulario


def _busca_corrigida(busca: str):
    """A busca com erro de digitação trocado pela palavra mais parecida.

    Só entra quando a busca original não achou nada, e só troca palavra que
    a loja não conhece: "cachoro" vira "cachorro", "racão" fica como está.
    Devolve None quando não há o que corrigir.
    """
    import difflib

    vocabulario = _vocabulario()
    corrigidas, mudou = [], False
    for palavra in _palavras_da_busca(busca):
        conhecida = (
            len(palavra) < 4
            or palavra in vocabulario
            or any(v.startswith(palavra) for v in vocabulario)
        )
        if conhecida:
            corrigidas.append(palavra)
            continue
        parecida = difflib.get_close_matches(palavra, vocabulario, n=1, cutoff=0.8)
        if parecida:
            corrigidas.append(parecida[0])
            mudou = True
        else:
            corrigidas.append(palavra)
    return " ".join(corrigidas) if mudou else None


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
    busca_corrigida = None
    busca_digitada = ""
    if busca:
        antes_da_busca = produtos
        produtos = produtos.filter(_condicao_de_busca(busca)).distinct()
        if not produtos.exists():
            # nada com o que foi digitado: tenta o erro de digitação mais
            # provável antes de dizer ao cliente que a loja não tem
            busca_corrigida = _busca_corrigida(busca)
            if busca_corrigida:
                produtos = antes_da_busca.filter(_condicao_de_busca(busca_corrigida)).distinct()
                busca_digitada, busca = busca, busca_corrigida
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

    # Quem buscou "ração" espera ver ração no topo, não um acessório que caiu
    # ali porque a linha dele se chama assim. A ordem na relevância é:
    # destaque escolhido pelo lojista, depois o que bate no nome do produto,
    # depois o resto. Com ordenação pedida pelo cliente (menor preço, mais
    # vendidos) nada disso vale: furar a fila que ele escolheu seria enganá-lo.
    if busca and ordem == "relevancia":
        from django.db.models import Case, IntegerField, Value, When

        produtos = produtos.annotate(
            _destaque=Case(
                When(pk__in=destacados, then=Value(0)),
                default=Value(1), output_field=IntegerField(),
            ),
            _no_nome=Case(
                When(_condicao_no_nome(busca), then=Value(0)),
                default=Value(1), output_field=IntegerField(),
            ),
        ).order_by("_destaque", "-prioridade_busca", "_no_nome", *ORDENACOES["relevancia"])

    paginator = Paginator(produtos, 24)
    pagina = paginator.get_page(request.GET.get("pagina"))

    # querystring sem o parâmetro de página, para os links do paginador
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(
        request,
        "catalog/catalogo.html",
        {
            "mostrar_assistente": True,
            "titulo": titulo,
            "pagina": pagina,
            "produtos": pagina.object_list,
            "total": paginator.count,
            # usado no estado vazio: "o catálogo tem N produtos esperando por você"
            "total_catalogo": Produto.objects.publicados().count(),
            "busca": busca,
            # "cachoro" virou "cachorro": a tela avisa, para o cliente não
            # achar que a loja leu errado
            "busca_digitada": busca_digitada,
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
    from django.db.models import Case, IntegerField, Q, Value, When
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
    for c in Categoria.objects.publicados().filter(
        Q(nome__icontains=termo) | Q(pk__in=_por_nome_sem_acento(Categoria, termo))
    )[:3]:
        atalhos.append({"rotulo": c.nome, "url": c.get_absolute_url(), "icone": "pacote",
                        "extra": f"{c.produtos.filter(publicado=True).count()} produtos"})
    for m in Marca.objects.publicados().filter(
        Q(nome__icontains=termo) | Q(pk__in=_por_nome_sem_acento(Marca, termo))
    )[:2]:
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

    # a prévia precisa achar o mesmo que o catálogo: quem digita "ração para
    # cachorro" e não vê nada na caixa acha que a loja não tem
    condicao = _condicao_de_busca(termo) | Q(sku__iexact=termo)
    if not Produto.objects.vitrine().filter(condicao).exists():
        corrigido = _busca_corrigida(termo)
        if corrigido:
            termo = corrigido
            condicao = _condicao_de_busca(termo)

    produtos = (
        Produto.objects.vitrine()
        .filter(condicao)
        .distinct()
        .annotate(
            _destaque=Case(
                When(pk__in=_produtos_em_destaque(termo), then=Value(0)),
                default=Value(1), output_field=IntegerField(),
            ),
            _no_nome=Case(
                When(_condicao_no_nome(termo), then=Value(0)),
                default=Value(1), output_field=IntegerField(),
            ),
        )
        .select_related("marca")
        .prefetch_related("imagens")
        .order_by("_destaque", "-prioridade_busca", "_no_nome", "-vendas", "nome")[:6]
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
