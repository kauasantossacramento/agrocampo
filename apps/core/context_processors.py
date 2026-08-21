from apps.catalog.models import Categoria
from apps.core.models import Pagina, SiteConfig


def site_context(request):
    """Injeta configuração da loja, menu e rodapé em todos os templates."""
    return {
        "site": SiteConfig.load(),
        "menu_categorias": Categoria.objects.menu(),
        "paginas_rodape": Pagina.objects.publicados().filter(ordem_rodape__gt=0),
    }
