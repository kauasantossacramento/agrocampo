"""Preservação do destino ao atravessar login, cadastro e endereço.

Quem estava fechando uma compra e precisou criar conta (ou cadastrar um
endereço) tem que voltar exatamente para onde parou. O parâmetro `next`
atravessa cada salto; este módulo centraliza a leitura e a validação dele.

Validar é obrigatório: um `next` vindo da query string é entrada do usuário.
Sem checagem, `?next=https://site-falso/` transformaria a nossa tela de login
num trampolim de phishing.
"""
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme

PARAMETRO = "next"


def destino_seguro(request, padrao="core:home"):
    """Devolve o `next` da requisição, ou o padrão se ele não for confiável."""
    bruto = request.POST.get(PARAMETRO) or request.GET.get(PARAMETRO) or ""
    if bruto and url_has_allowed_host_and_scheme(
        url=bruto,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return bruto
    try:
        return reverse(padrao)
    except NoReverseMatch:
        return padrao


def com_destino(url, destino):
    """Anexa `?next=destino` a uma URL, sem duplicar o parâmetro."""
    if not destino:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}{PARAMETRO}={destino}"
