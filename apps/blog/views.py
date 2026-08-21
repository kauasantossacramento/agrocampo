from django.core.paginator import Paginator
from django.db.models import F
from django.shortcuts import get_object_or_404, render

from .models import CategoriaPost, Post


def lista(request, categoria=None):
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
