"""Home, páginas institucionais e newsletter."""
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.blog.models import Post
from apps.catalog.models import Categoria, Especie, Marca, Produto

from .models import PromocaoDestaque, AssinanteNewsletter, Banner, Diferencial, Pagina, SiteConfig


def _promocoes_por_secao():
    """{chave_da_secao: [promoções vigentes]} — só o que está no prazo."""
    agora = timezone.now()
    grupos = {}
    for promo in (
        PromocaoDestaque.objects.filter(ativo=True, inicio__lte=agora, fim__gte=agora)
        .select_related("produto")
    ):
        grupos.setdefault(promo.posicao, []).append(promo)
    return grupos


def home(request):
    config = SiteConfig.load()
    produtos = Produto.objects.vitrine()
    agora = timezone.now()

    # `preco_promocional` preenchido não basta: quando o produto tem tamanhos,
    # quem manda no preço é a variação, e a oferta virava "de R$ 289,90 por
    # R$ 289,90". O filtro final é `promocao_vigente`, que já sabe disso.
    candidatas = (
        produtos.filter(preco_promocional__isnull=False)
        .prefetch_related("variacoes")
        .order_by("promocao_ate")
    )
    ofertas = [p for p in candidatas[:30] if p.promocao_vigente][:10]

    oferta_relampago = next(
        (
            p
            for p in candidatas.filter(promocao_ate__gt=agora)[:30]
            if p.promocao_vigente
        ),
        None,
    )

    # uma vitrine por linha, só as que o lojista deixou ligadas e têm produto
    vitrines = []
    for config_vitrine in config.vitrines_por_linha():
        if not config_vitrine["ativa"]:
            continue
        itens = produtos.da_linha(config_vitrine["linha"]).order_by("-vendas", "-destaque")[:8]
        if itens:
            vitrines.append({**config_vitrine, "produtos": itens})

    template = (
        "core/home_vitrine.html"
        if config.layout_home == SiteConfig.LayoutHome.VITRINE
        else "core/home.html"
    )
    return render(
        request,
        template,
        {
            "mostrar_assistente": True,
            # quatro banners menores, "ofertas em destaque" do estilo vitrine
            # "Ofertas em destaque": cartazes que o lojista liga e desliga
            # (publicado). Um ocupa a largura toda; dois ficam lado a lado.
            "banners_secundarios": [
                b for b in Banner.objects.publicados()
                .filter(posicao=Banner.Posicao.SECUNDARIO)
                .order_by("ordem", "-criado_em") if b.imagem
            ],
            "vitrines_linha": vitrines,
            "banners": Banner.objects.publicados().filter(posicao=Banner.Posicao.HERO),
            # carrossel do estilo vitrine: cartazes + vídeos/fotos de apresentação,
            # numa fita só, na ordem de cadastro
            "slides": list(
                Banner.objects.publicados()
                .filter(posicao__in=[Banner.Posicao.HERO, Banner.Posicao.APRESENTACAO])
                .prefetch_related("produtos")
                .order_by("ordem", "-criado_em")
            ),
            # com apresentação cadastrada ela assume o topo; sem ela, o hero
            # antigo entra em versão compacta no celular.
            # Só entram os que têm vídeo ou foto: um banner sem mídia não
            # rende slide, mas contaria para a barra de pontos.
            "apresentacao": [
                b
                for b in Banner.objects.publicados()
                .filter(posicao=Banner.Posicao.APRESENTACAO)
                .prefetch_related("produtos")
                if b.tem_midia
            ],
            "faixas_produto": (
                Banner.objects.publicados()
                .filter(posicao=Banner.Posicao.PRODUTOS)
                .prefetch_related("produtos__imagens")
            ),
            "diferenciais": Diferencial.objects.publicados(),
            "categorias_destaque": Categoria.objects.publicados().filter(destaque_home=True)[:6],
            # Maiores sucessos: marcação manual no produto ou marca inteira
            "mais_vendidos": produtos.filter(
                Q(destaque=True) | Q(marca__sucesso=True)
            ).distinct().order_by("-vendas", "-criado_em")[:8],
            # ordem das seções e promoções vigentes por posição (estilo vitrine)
            "secoes_home": [f"core/secoes/{c}.html" for c in config.secoes_home()],
            "promocoes_por_secao": _promocoes_por_secao(),
            "lancamentos": produtos.filter(lancamento=True)[:8],
            "assinaveis": produtos.filter(permite_assinatura=True)[:4],
            "ofertas": ofertas,
            "oferta_relampago": oferta_relampago,
            "especies": Especie.objects.publicados().filter(destaque_home=True)[:24],
            "marcas": Marca.objects.publicados().filter(destaque=True)[:18],
            "posts": Post.objects.visiveis()[:3] if config.blog_ativo else [],
        },
    )


def pagina(request, slug):
    return render(
        request,
        "core/pagina.html",
        {"pagina": get_object_or_404(Pagina.objects.publicados(), slug=slug)},
    )


@require_POST
def newsletter(request):
    email = (request.POST.get("email") or "").strip().lower()
    if not email:
        mensagem, ok = "Informe um e-mail válido.", False
    else:
        AssinanteNewsletter.objects.get_or_create(
            email=email, defaults={"nome": request.POST.get("nome", "")}
        )
        mensagem, ok = "Pronto! Você vai receber nossas ofertas.", True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": ok, "mensagem": mensagem})

    (messages.success if ok else messages.error)(request, mensagem)
    return redirect(request.META.get("HTTP_REFERER", "core:home"))


def service_worker(request):
    """Serve o SW a partir da raiz.

    Um service worker so controla URLs abaixo do proprio caminho. Servido de
    /static/sw.js ele nao poderia controlar a loja inteira, e o navegador
    recusava o registro.
    """
    from django.conf import settings
    from django.http import FileResponse

    caminho = settings.BASE_DIR / "static" / "sw.js"
    return FileResponse(open(caminho, "rb"), content_type="application/javascript")


def offline(request):
    """Página servida pelo service worker quando não há conexão."""
    return render(request, "core/offline.html")
