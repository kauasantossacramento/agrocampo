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


class SeloProteinaELinhasTests(TestCase):
    """Selo da linha (nome editável), faixa de proteína e estoque infinito."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Produto
        from apps.core.models import SiteConfig

        categoria = Categoria.objects.create(nome="Ração", exibir_no_menu=True)
        self.produto = Produto.objects.create(
            sku="R-1", nome="Ração Special Care 15kg", categoria=categoria,
            preco=Decimal("289.90"), publicado=True, linha="ouro", proteina=26,
        )
        self.config = SiteConfig.load()

    def test_produto_novo_ja_nasce_sem_contagem(self):
        from apps.catalog.models import Produto

        novo = Produto.objects.create(sku="X-1", nome="Novo", categoria=self.produto.categoria,
                                      preco=10, publicado=True)
        self.assertTrue(novo.sem_controle_estoque)
        self.assertTrue(novo.em_estoque)

    def test_nomes_padrao_das_linhas(self):
        self.assertEqual(self.config.linha_ouro_nome, "Super Premium")
        self.assertEqual(self.config.linha_prata_nome, "Premium")
        self.assertEqual(self.config.linha_bronze_nome, "")
        self.assertEqual(self.produto.linha_nome, "Super Premium")

    def test_lojista_renomeia_a_linha(self):
        self.config.linha_ouro_nome = "Linha Ouro Especial"
        self.config.save()
        self.produto.refresh_from_db()
        html = self.client.get(self.produto.get_absolute_url()).content.decode()
        self.assertIn("Linha Ouro Especial", html)
        self.assertNotIn("Super Premium", html)

    def test_linha_sem_nome_nao_mostra_selo(self):
        self.produto.linha = "bronze"
        self.produto.save()
        self.assertEqual(self.produto.linha_nome, "")
        html = self.client.get("/catalogo/").content.decode()
        self.assertNotIn("selo-linha selo-linha--bronze", html)

    def test_selo_aparece_no_card_e_na_pagina(self):
        html = self.client.get("/catalogo/").content.decode()
        self.assertIn("selo-linha--ouro", html)
        self.assertIn("Super Premium", html)
        html = self.client.get(self.produto.get_absolute_url()).content.decode()
        self.assertIn("selo-linha--ouro", html)

    def test_faixa_de_proteina(self):
        html = self.client.get("/catalogo/").content.decode()
        self.assertIn("faixa-proteina", html)
        self.assertIn("26%", html)
        html = self.client.get(self.produto.get_absolute_url()).content.decode()
        self.assertIn("faixa-proteina--grande", html)

    def test_sem_proteina_nao_mostra_faixa(self):
        self.produto.proteina = None
        self.produto.save()
        self.assertNotIn("faixa-proteina", self.client.get("/catalogo/").content.decode())
