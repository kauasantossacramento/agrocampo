from apps.catalog.models import Categoria
from apps.core.models import Pagina, SiteConfig


def site_context(request):
    """Injeta configuração da loja, menu e rodapé em todos os templates."""
    from apps.payments.models import ProvedorPagamento

    return {
        "site": SiteConfig.load(),
        # Fonte única do parcelamento: quem manda é o adquirente, porque é ele
        # que aceita ou recusa a quantidade de parcelas na hora de cobrar.
        "provedor_pagamento": ProvedorPagamento.ativo_padrao(),
        "menu_categorias": Categoria.objects.menu(),
        "paginas_rodape": Pagina.objects.publicados().filter(ordem_rodape__gt=0),
    }
