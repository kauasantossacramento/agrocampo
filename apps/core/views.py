"""Home, páginas institucionais e newsletter."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.blog.models import Post
from apps.catalog.models import Categoria, Especie, Marca, Produto

from .models import AssinanteNewsletter, Banner, Diferencial, Pagina


def home(request):
    produtos = Produto.objects.vitrine()
    agora = timezone.now()

    ofertas = produtos.filter(preco_promocional__isnull=False).order_by("promocao_ate")[:10]
    oferta_relampago = (
        produtos.filter(preco_promocional__isnull=False, promocao_ate__gt=agora)
        .order_by("promocao_ate")
        .first()
    )

    return render(
        request,
        "core/home.html",
        {
            "banners": Banner.objects.publicados().filter(posicao=Banner.Posicao.HERO),
            "diferenciais": Diferencial.objects.publicados(),
            "categorias_destaque": Categoria.objects.publicados().filter(destaque_home=True)[:6],
            "mais_vendidos": produtos.filter(destaque=True)[:8],
            "lancamentos": produtos.filter(lancamento=True)[:8],
            "assinaveis": produtos.filter(permite_assinatura=True)[:4],
            "ofertas": ofertas,
            "oferta_relampago": oferta_relampago,
            "especies": Especie.objects.publicados().filter(destaque_home=True)[:14],
            "marcas": Marca.objects.publicados().filter(destaque=True)[:18],
            "posts": Post.objects.visiveis()[:3],
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


def offline(request):
    """Página servida pelo service worker quando não há conexão."""
    return render(request, "core/offline.html")
