from django.core.paginator import Paginator
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.core.models import SiteConfig


def _exigir_blog_ativo():
    """Com o blog desligado no admin, as URLs somem de verdade (404)."""
    if not SiteConfig.load().blog_ativo:
        raise Http404("O blog está desativado.")

from .models import CategoriaPost, Post


def lista(request, categoria=None):
    _exigir_blog_ativo()
    posts = Post.objects.visiveis().select_related("categoria", "autor")
    if categoria:
        posts = posts.filter(categoria=categoria)
    pagina = Paginator(posts, 9).get_page(request.GET.get("pagina"))
    return render(
        request,
        "blog/lista.html",
        {
            "pagina": pagina,
            "posts": pagina.object_list,
            "categorias": CategoriaPost.objects.all(),
            "categoria_atual": categoria,
        },
    )


def por_categoria(request, slug):
    return lista(request, categoria=get_object_or_404(CategoriaPost, slug=slug))


def detalhe(request, slug):
    _exigir_blog_ativo()
    post = get_object_or_404(
        Post.objects.visiveis().prefetch_related("produtos_relacionados__imagens"),
        slug=slug,
    )
    Post.objects.filter(pk=post.pk).update(visualizacoes=F("visualizacoes") + 1)
    return render(
        request,
        "blog/detalhe.html",
        {
            "post": post,
            "relacionados": Post.objects.visiveis().exclude(pk=post.pk)[:3],
        },
    )
