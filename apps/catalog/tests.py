"""Testes do catálogo."""
from django.test import TestCase


class ListagensNaoFicamVaziasTests(TestCase):
    """Regressão: a loja aparecia vazia quando o estoque era zero."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Produto

        self.racao = Categoria.objects.create(nome="Ração", exibir_no_menu=True)
        self.filha = Categoria.objects.create(nome="Cães", pai=self.racao, exibir_no_menu=True)
        self.vazia = Categoria.objects.create(nome="Acessórios", exibir_no_menu=True)
        self.produto = Produto.objects.create(
            sku="R-1", nome="Ração Golden 15kg", categoria=self.filha,
            preco=Decimal("289.90"), estoque=0, sem_controle_estoque=True, publicado=True,
        )

    def test_filtro_somente_disponiveis_inclui_sob_encomenda(self):
        r = self.client.get("/catalogo/", {"disponivel": "1"})
        self.assertContains(r, "Ração Golden 15kg")

    def test_filtro_somente_disponiveis_ainda_esconde_esgotado(self):
        self.produto.sem_controle_estoque = False
        self.produto.save()
        r = self.client.get("/catalogo/", {"disponivel": "1"})
        self.assertNotContains(r, "Ração Golden 15kg")

    def test_menu_esconde_categoria_sem_produto(self):
        from apps.catalog.models import Categoria

        menu = list(Categoria.objects.menu())
        self.assertIn(self.racao, menu)      # tem produto numa filha
        self.assertNotIn(self.vazia, menu)   # vazia some até ganhar produto

    def test_categoria_ganha_produto_e_volta_ao_menu(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Produto

        Produto.objects.create(sku="A-1", nome="Comedouro", categoria=self.vazia,
                               preco=Decimal("50"), publicado=True)
        self.assertIn(self.vazia, list(Categoria.objects.menu()))

    def test_pagina_vazia_oferece_o_catalogo_inteiro(self):
        r = self.client.get(self.vazia.get_absolute_url())
        self.assertContains(r, "Ver todos os produtos")
        self.assertContains(r, "1 produto")
