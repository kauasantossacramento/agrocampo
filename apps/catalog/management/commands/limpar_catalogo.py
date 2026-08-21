"""Limpa o catálogo para o lojista começar do zero.

    python manage.py limpar_catalogo --sem-imagem     # só produtos sem foto
    python manage.py limpar_catalogo --produtos       # todos os produtos
    python manage.py limpar_catalogo --tudo           # produtos + categorias/marcas/espécies
    python manage.py limpar_catalogo --zerar-estoque  # mantém produtos, zera estoque

Produtos que já aparecem em algum pedido não são apagados (a FK é PROTECT e
o histórico precisa continuar íntegro) — eles são despublicados.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError

from apps.catalog.models import (
    Avaliacao,
    Categoria,
    Especie,
    ListaDesejos,
    Marca,
    MovimentoEstoque,
    Produto,
    ProdutoImagem,
)


def limpar(*, produtos=False, sem_imagem=False, tudo=False, zerar_estoque=False):
    """Executa a limpeza e devolve um resumo do que aconteceu."""
    resumo = {"apagados": 0, "despublicados": 0, "zerados": 0, "auxiliares": 0}

    with transaction.atomic():
        if zerar_estoque:
            resumo["zerados"] = Produto.objects.update(estoque=0)

        alvo = None
        if sem_imagem:
            alvo = Produto.objects.filter(imagens__isnull=True)
        elif produtos or tudo:
            alvo = Produto.objects.all()

        if alvo is not None:
            for produto in list(alvo):
                try:
                    with transaction.atomic():
                        ListaDesejos.objects.filter(produto=produto).delete()
                        Avaliacao.objects.filter(produto=produto).delete()
                        MovimentoEstoque.objects.filter(produto=produto).delete()
                        ProdutoImagem.objects.filter(produto=produto).delete()
                        produto.delete()
                        resumo["apagados"] += 1
                except ProtectedError:
                    # está em pedido ou assinatura: preserva o histórico
                    Produto.objects.filter(pk=produto.pk).update(publicado=False, estoque=0)
                    resumo["despublicados"] += 1

        if tudo:
            resumo["auxiliares"] += Categoria.objects.filter(produtos__isnull=True).delete()[0]
            resumo["auxiliares"] += Marca.objects.filter(produtos__isnull=True).delete()[0]
            resumo["auxiliares"] += Especie.objects.filter(produtos__isnull=True).delete()[0]

    return resumo


class Command(BaseCommand):
    help = "Apaga produtos (e opcionalmente categorias/marcas/espécies) do catálogo."

    def add_arguments(self, parser):
        parser.add_argument("--sem-imagem", action="store_true",
                            help="Apaga apenas os produtos que não têm nenhuma foto.")
        parser.add_argument("--produtos", action="store_true", help="Apaga todos os produtos.")
        parser.add_argument("--tudo", action="store_true",
                            help="Apaga produtos e as categorias/marcas/espécies que ficarem órfãs.")
        parser.add_argument("--zerar-estoque", action="store_true",
                            help="Mantém os produtos e zera o estoque de todos.")
        parser.add_argument("--sim", action="store_true", help="Não pede confirmação.")

    def handle(self, *args, **o):
        if not any([o["sem_imagem"], o["produtos"], o["tudo"], o["zerar_estoque"]]):
            self.stdout.write(self.style.ERROR(
                "Escolha uma ação: --sem-imagem, --produtos, --tudo ou --zerar-estoque"
            ))
            return

        if not o["sim"]:
            total = Produto.objects.count()
            self.stdout.write(self.style.WARNING(
                f"Isso vai mexer no catálogo ({total} produtos). Rode com --sim para confirmar."
            ))
            return

        resumo = limpar(
            produtos=o["produtos"], sem_imagem=o["sem_imagem"],
            tudo=o["tudo"], zerar_estoque=o["zerar_estoque"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"{resumo['apagados']} produto(s) apagado(s), "
            f"{resumo['despublicados']} despublicado(s) por estarem em pedidos, "
            f"{resumo['zerados']} com estoque zerado, "
            f"{resumo['auxiliares']} registro(s) auxiliar(es) removido(s)."
        ))
