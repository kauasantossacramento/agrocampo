"""Resolução do carrinho ativo a partir da requisição."""
from django.conf import settings

from .models import Carrinho


def obter_carrinho(request, criar=True):
    """Devolve o carrinho do usuário logado ou o da sessão anônima."""
    if request.user.is_authenticated:
        carrinho = (
            Carrinho.objects.filter(usuario=request.user, finalizado=False)
            .prefetch_related("itens__produto")
            .first()
        )
        if not carrinho and criar:
            carrinho = Carrinho.objects.create(usuario=request.user)
        return carrinho

    if not request.session.session_key:
        if not criar:
            return None
        request.session.create()

    chave = request.session.session_key
    carrinho = Carrinho.objects.filter(chave_sessao=chave, finalizado=False).first()
    if not carrinho and criar:
        carrinho = Carrinho.objects.create(chave_sessao=chave)
    return carrinho


def mesclar_apos_login(request, usuario):
    """Chamado no login: junta o carrinho anônimo ao carrinho do usuário."""
    chave = request.session.session_key
    if not chave:
        return None
    anonimo = Carrinho.objects.filter(chave_sessao=chave, usuario__isnull=True,
                                      finalizado=False).first()
    if not anonimo:
        return None
    do_usuario = Carrinho.objects.filter(usuario=usuario, finalizado=False).first()
    if not do_usuario:
        anonimo.usuario = usuario
        anonimo.chave_sessao = ""
        anonimo.save(update_fields=["usuario", "chave_sessao"])
        return anonimo
    return do_usuario.mesclar(anonimo)


CART_SESSION_KEY = getattr(settings, "CART_SESSION_KEY", "agrocampo_cart_id")
