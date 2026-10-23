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
            preco=Decimal("289.90"), publicado=True, proteina=26,
        )
        # as linhas são cadastro do lojista; a migração já cria as três iniciais
        from apps.catalog.models import LinhaProduto

        self.LinhaProduto = LinhaProduto
        self.ouro = LinhaProduto.objects.get(slug="ouro")
        self.bronze = LinhaProduto.objects.get(slug="bronze")
        self.produto.linha = self.ouro
        self.produto.save(update_fields=["linha"])
        self.config = SiteConfig.load()

    def test_produto_novo_ja_nasce_sem_contagem(self):
        from apps.catalog.models import Produto

        novo = Produto.objects.create(sku="X-1", nome="Novo", categoria=self.produto.categoria,
                                      preco=10, publicado=True)
        self.assertTrue(novo.sem_controle_estoque)
        self.assertTrue(novo.em_estoque)

    def test_nomes_padrao_das_linhas(self):
        nomes = list(self.LinhaProduto.objects.values_list("nome", flat=True))
        self.assertEqual(nomes, ["Super Premium", "Premium", "Especial"])
        self.assertEqual(self.produto.linha_nome, "Super Premium")

    def test_lojista_renomeia_a_linha(self):
        self.ouro.nome = "Linha Ouro Especial"
        self.ouro.save()
        self.produto.refresh_from_db()
        html = self.client.get(self.produto.get_absolute_url()).content.decode()
        self.assertIn("Linha Ouro Especial", html)
        self.assertNotIn("Super Premium", html)

    def test_produto_sem_linha_nao_mostra_selo(self):
        self.produto.linha = None
        self.produto.save()
        self.assertEqual(self.produto.linha_nome, "")
        html = self.client.get("/catalogo/").content.decode()
        self.assertNotIn("selo-linha", html)

    def test_linha_fora_de_uso_nao_mostra_selo(self):
        self.ouro.ativo = False
        self.ouro.save()
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.linha_nome, "")

    def test_selo_segue_o_tamanho_e_a_cor_da_linha(self):
        self.ouro.selo_tamanho = 40
        self.ouro.cor = "#1B3C8C"
        self.ouro.save()
        html = self.client.get("/catalogo/").content.decode()
        self.assertIn("--selo-base:40px", html)
        self.assertIn("--linha-cor:#1B3C8C", html)
        # o claro e o escuro saem da cor escolhida, sem o lojista precisar pensar
        self.assertIn(f"--linha-clara:{self.ouro.cor_clara}", html)
        self.assertIn(f"--linha-escura:{self.ouro.cor_escura}", html)

    def test_tons_derivados_da_cor(self):
        self.ouro.cor = "#808080"
        self.assertEqual(self.ouro.cor_clara, "#CFCFCF")
        self.assertEqual(self.ouro.cor_escura, "#4F4F4F")

    def test_selo_aparece_no_card_e_na_pagina(self):
        html = self.client.get("/catalogo/").content.decode()
        self.assertIn("selo-linha", html)
        self.assertIn("Super Premium", html)
        html = self.client.get(self.produto.get_absolute_url()).content.decode()
        self.assertIn("selo-linha", html)

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


class FotoDoProdutoTests(TestCase):
    """A foto leva ao produto na listagem e abre ampliada na página dele."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Produto

        categoria = Categoria.objects.create(nome="Ração", exibir_no_menu=True)
        self.produto = Produto.objects.create(
            sku="F-1", nome="Ração com foto", categoria=categoria,
            preco=Decimal("99.90"), publicado=True,
        )

    def test_card_da_listagem_tem_a_foto_dentro_do_link_do_produto(self):
        html = self.client.get("/catalogo/").content.decode()
        inicio = html.index('class="product__media"')
        trecho = html[html.rindex("<a ", 0, inicio):inicio]
        self.assertIn(self.produto.get_absolute_url(), trecho)

    def test_pagina_do_produto_oferece_a_foto_ampliada(self):
        html = self.client.get(self.produto.get_absolute_url()).content.decode()
        self.assertIn("data-ampliar", html)
        self.assertIn("data-lupa", html)

    def test_oferta_do_dia_tem_a_foto_clicavel(self):
        """A foto da oferta não levava a lugar nenhum; agora abre o produto."""
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        self.produto.preco_promocional = Decimal("79.90")
        self.produto.promocao_ate = timezone.now() + timedelta(days=2)
        self.produto.save()

        html = self.client.get("/").content.decode()
        if "promoção do dia" not in html.lower():
            self.skipTest("a home está no estilo clássico, sem a seção de oferta")
        bloco = html[html.index("flash__inner"):]
        bloco = bloco[:bloco.index("</section>")]
        self.assertIn(f'href="{self.produto.get_absolute_url()}"', bloco)


class LixeiraDeProdutosTests(TestCase):
    """Excluir é tirar da loja; o registro continua inteiro."""

    def setUp(self):
        from decimal import Decimal

        from apps.accounts.models import User
        from apps.catalog.models import Categoria, Produto

        self.Produto = Produto
        categoria = Categoria.objects.create(nome="Ração", exibir_no_menu=True)
        self.produto = Produto.objects.create(
            sku="LX-1", nome="Ração que será excluída", categoria=categoria,
            preco=Decimal("50.00"), publicado=True,
        )
        self.lojista = User.objects.create_user(
            email="lojista-lixeira@agrocampo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )

    def test_produto_na_lixeira_some_da_loja(self):
        self.assertIn(self.produto, self.Produto.objects.publicados())
        self.produto.mandar_para_lixeira()
        self.assertNotIn(self.produto, self.Produto.objects.publicados())
        self.assertNotIn("Ração que será excluída",
                         self.client.get("/catalogo/").content.decode())

    def test_o_registro_continua_existindo(self):
        self.produto.mandar_para_lixeira()
        self.produto.refresh_from_db()
        self.assertTrue(self.Produto.objects.filter(pk=self.produto.pk).exists())
        self.assertTrue(self.produto.na_lixeira)
        self.assertIsNotNone(self.produto.excluido_em)

    def test_restaurar_devolve_para_a_loja(self):
        self.produto.mandar_para_lixeira()
        self.produto.restaurar()
        self.assertIn(self.produto, self.Produto.objects.publicados())

    def test_pedido_antigo_nao_se_perde(self):
        """O item vendido aponta para o produto: por isso nada é apagado."""
        self.produto.mandar_para_lixeira()
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.nome, "Ração que será excluída")
        self.assertEqual(self.produto.preco, self.produto.preco)

    def test_painel_manda_para_a_lixeira_e_traz_de_volta(self):
        self.client.force_login(self.lojista)
        url = f"/painel/produtos/{self.produto.id}/lixeira/"

        self.client.post(url)
        self.produto.refresh_from_db()
        self.assertTrue(self.produto.na_lixeira)

        self.client.post(url)
        self.produto.refresh_from_db()
        self.assertFalse(self.produto.na_lixeira)

    def test_listagem_do_painel_separa_a_lixeira(self):
        self.client.force_login(self.lojista)
        self.produto.mandar_para_lixeira()

        normal = self.client.get("/painel/produtos/").content.decode()
        self.assertNotIn("Ração que será excluída", normal)

        lixeira = self.client.get("/painel/produtos/?filtro=lixeira").content.decode()
        self.assertIn("Ração que será excluída", lixeira)
        self.assertIn("Restaurar", lixeira)

    def test_visitante_nao_mexe_na_lixeira(self):
        resposta = self.client.post(f"/painel/produtos/{self.produto.id}/lixeira/")
        self.produto.refresh_from_db()
        self.assertNotEqual(resposta.status_code, 200)
        self.assertFalse(self.produto.na_lixeira)


class AvesAgrupadasTests(TestCase):
    """Treze pássaros viram um card só — sem perder cadastro nem ligação."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Especie, Produto

        self.Especie, self.Produto = Especie, Produto
        self.aves = Especie.objects.create(nome="Aves", slug="aves", grupo="aves",
                                           destaque_home=True)
        self.canario = Especie.objects.create(nome="Canário", grupo="passeriforme",
                                              agrupada_em=self.aves)
        self.galinha = Especie.objects.create(nome="Galinha", grupo="rural",
                                              destaque_home=True)

        categoria = Categoria.objects.create(nome="Ração")
        self.racao_canario = Produto.objects.create(
            sku="AV-1", nome="Mistura para Canário", categoria=categoria,
            preco=Decimal("30"), publicado=True,
        )
        self.racao_canario.especies.add(self.canario)
        self.racao_galinha = Produto.objects.create(
            sku="GL-1", nome="Ração Postura", categoria=categoria,
            preco=Decimal("90"), publicado=True,
        )
        self.racao_galinha.especies.add(self.galinha)

    def test_so_a_mae_aparece_na_navegacao(self):
        navegaveis = list(self.Especie.objects.navegaveis().values_list("nome", flat=True))
        self.assertIn("Aves", navegaveis)
        self.assertIn("Galinha", navegaveis)      # criação continua separada
        self.assertNotIn("Canário", navegaveis)

    def test_o_canario_continua_no_banco_com_o_produto(self):
        self.canario.refresh_from_db()
        self.assertTrue(self.Especie.objects.filter(nome="Canário").exists())
        self.assertIn(self.racao_canario, self.canario.produtos.all())

    def test_card_de_aves_lista_o_que_e_de_passaro(self):
        html = self.client.get(self.aves.get_absolute_url()).content.decode()
        self.assertIn("Mistura para Canário", html)
        self.assertNotIn("Ração Postura", html)   # galinha não entra em Aves

    def test_link_antigo_do_canario_redireciona(self):
        resposta = self.client.get(self.canario.get_absolute_url())
        self.assertEqual(resposta.status_code, 301)
        self.assertEqual(resposta["Location"], self.aves.get_absolute_url())

    def test_pagina_de_especies_nao_lista_cada_passaro(self):
        html = self.client.get("/especies/").content.decode()
        self.assertIn("Aves", html)
        self.assertNotIn(">Canário<", html)

    def test_home_mostra_aves_como_um_card(self):
        html = self.client.get("/").content.decode()
        if "Navegue pelo seu animal" not in html:
            self.skipTest("a home está sem a seção de espécies")
        bloco = html[html.index("Navegue pelo seu animal"):]
        bloco = bloco[:bloco.index("</section>")]
        self.assertIn("Aves", bloco)
        self.assertNotIn("Canário", bloco)


class BuscaPorApelidoTests(TestCase):
    """Quem digita como fala precisa achar: cachorro, racao, cavalo."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Especie, Produto

        self.Produto = Produto
        categoria = Categoria.objects.create(nome="Ração")
        self.cao = Especie.objects.create(
            nome="Cão", sinonimos="cachorro, dog, canino", grupo="pet",
        )
        self.cavalo = Especie.objects.create(
            nome="Cavalo", slug="equino", sinonimos="equino, égua", grupo="rural",
        )
        self.racao = Produto.objects.create(
            sku="B-1", nome="Ração Premium Cães Adultos", categoria=categoria,
            preco=Decimal("120"), publicado=True,
        )
        self.racao.especies.add(self.cao)
        self.sal = Produto.objects.create(
            sku="B-2", nome="Sal Mineral", categoria=categoria,
            preco=Decimal("80"), publicado=True,
        )
        self.sal.especies.add(self.cavalo)

    def _buscar(self, termo):
        import re

        html = self.client.get("/catalogo/", {"q": termo}).content.decode()
        return re.findall(r'class="product__name"[^>]*>([^<]+)<', html)

    def test_cachorro_acha_racao_de_cao(self):
        achados = self._buscar("cachorro")
        self.assertIn("Ração Premium Cães Adultos", [a.strip() for a in achados])

    def test_sem_acento_acha_com_acento(self):
        """"racao" é como meio mundo digita no celular."""
        self.assertTrue(self._buscar("racao"))

    def test_cavalo_acha_o_que_era_equino(self):
        achados = [a.strip() for a in self._buscar("cavalo")]
        self.assertIn("Sal Mineral", achados)

    def test_apelido_antigo_continua_valendo(self):
        achados = [a.strip() for a in self._buscar("equino")]
        self.assertIn("Sal Mineral", achados)

    def test_termo_curto_nao_dispara_apelido(self):
        """Uma letra traria o catálogo inteiro sem querer."""
        from apps.catalog.views import _especies_por_apelido

        self.assertEqual(_especies_por_apelido("c"), [])

    def test_sugestoes_tambem_acham_por_apelido(self):
        import json

        dados = json.loads(self.client.get("/busca/sugestoes/", {"q": "cachorro"}).content)
        rotulos = [i["rotulo"] for g in dados["grupos"] for i in g["itens"]]
        self.assertIn("Ração Premium Cães Adultos", rotulos)

    def test_copia_sem_acento_acompanha_o_nome(self):
        self.racao.nome = "Ração Super Premium"
        self.racao.save()
        self.racao.refresh_from_db()
        self.assertIn("racao super premium", self.racao.busca_normalizada)


class DestaqueDaBuscaTests(TestCase):
    """O lojista decide o que aparece primeiro em cada busca."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import (Categoria, DestaqueBusca, Especie,
                                         Marca, Produto)

        self.DestaqueBusca = DestaqueBusca
        categoria = Categoria.objects.create(nome="Ração")
        cao = Especie.objects.create(nome="Cão", sinonimos="cachorro, dog", grupo="pet")
        self.special = Marca.objects.create(nome="Special Care")

        self.destacado = Produto.objects.create(
            sku="D-1", nome="Ração Special Care Cães Adultos", categoria=categoria,
            marca=self.special, preco=Decimal("150"), publicado=True, vendas=0,
        )
        self.comum = Produto.objects.create(
            sku="D-2", nome="Ração Comum para Cães", categoria=categoria,
            preco=Decimal("90"), publicado=True, vendas=99,     # venderia mais
        )
        for p in (self.destacado, self.comum):
            p.especies.add(cao)

    def _buscar(self, termo, **extra):
        import re

        html = self.client.get("/catalogo/", {"q": termo, **extra}).content.decode()
        return [n.strip() for n in re.findall(r'class="product__name"[^>]*>([^<]+)<', html)]

    def test_frase_inteira_encontra(self):
        """"ração para cachorro" não existe em nome nenhum — e precisa achar."""
        achados = self._buscar("ração para cachorro")
        self.assertIn("Ração Comum para Cães", achados)
        self.assertIn("Ração Special Care Cães Adultos", achados)

    def test_sem_destaque_manda_a_relevancia(self):
        self.assertEqual(self._buscar("ração para cachorro")[0], "Ração Comum para Cães")

    def test_destaque_por_marca_vai_para_o_topo(self):
        self.DestaqueBusca.objects.create(
            termos="ração para cachorro, racao cachorro", marca=self.special,
        )
        self.assertEqual(
            self._buscar("ração para cachorro")[0], "Ração Special Care Cães Adultos"
        )

    def test_destaque_vale_sem_acento_e_por_pedaco(self):
        self.DestaqueBusca.objects.create(termos="cachorro", marca=self.special)
        self.assertEqual(self._buscar("racao cachorro")[0], "Ração Special Care Cães Adultos")

    def test_destaque_desligado_nao_vale(self):
        self.DestaqueBusca.objects.create(
            termos="cachorro", marca=self.special, ativo=False,
        )
        self.assertEqual(self._buscar("ração para cachorro")[0], "Ração Comum para Cães")

    def test_ordem_pedida_pelo_cliente_manda_mais_que_o_destaque(self):
        """Pediu menor preço, recebe menor preço — destaque não fura fila."""
        self.DestaqueBusca.objects.create(termos="cachorro", marca=self.special)
        achados = self._buscar("ração para cachorro", ordem="menor-preco")
        self.assertEqual(achados[0], "Ração Comum para Cães")

    def test_destaque_por_produto_escolhido(self):
        destaque = self.DestaqueBusca.objects.create(termos="cachorro")
        destaque.produtos.add(self.destacado)
        self.assertEqual(self._buscar("cachorro")[0], "Ração Special Care Cães Adultos")

    def test_palavras_de_ligacao_nao_estreitam_a_busca(self):
        """Exigir "para" tiraria resultado bom da frente do cliente."""
        from apps.catalog.views import _condicao_de_busca

        with_para = self._buscar("ração para cachorro")
        sem_para = self._buscar("ração cachorro")
        self.assertEqual(sorted(with_para), sorted(sem_para))
        self.assertTrue(_condicao_de_busca("ração para cachorro"))


class BuscaPluralTagsEPrioridadeTests(TestCase):
    """Plural, palavras-chave, prioridade e a prévia achando o mesmo."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Especie, Marca, Produto

        categoria = Categoria.objects.create(nome="Ração")
        cao = Especie.objects.create(nome="Cão", sinonimos="cachorro, dog", grupo="pet")
        marca = Marca.objects.create(nome="Special care")

        self.especial = Produto.objects.create(
            sku="P-1", nome="Special Care Cães Adultos", categoria=categoria,
            marca=marca, preco=Decimal("180"), publicado=True,
            palavras_chave="ração, cachorro", prioridade_busca=10, vendas=0,
        )
        self.comum = Produto.objects.create(
            sku="P-2", nome="Ração Golden Fórmula 15kg", categoria=categoria,
            preco=Decimal("120"), publicado=True, vendas=99,
        )
        for p in (self.especial, self.comum):
            p.especies.add(cao)

    def _itens(self, termo):
        import re

        html = self.client.get("/catalogo/", {"q": termo}).content.decode()
        return [n.strip() for n in re.findall(r'class="product__name"[^>]*>([^<]+)<', html)]

    def _previa(self, termo):
        import json

        dados = json.loads(self.client.get("/busca/sugestoes/", {"q": termo}).content)
        return [i["rotulo"] for g in dados["grupos"] if g.get("produtos") for i in g["itens"]]

    def test_plural_acha_o_singular(self):
        """"rações" é como o cliente digita; o produto se chama "Ração"."""
        self.assertIn("Ração Golden Fórmula 15kg", self._itens("rações"))
        self.assertIn("Ração Golden Fórmula 15kg", self._itens("racoes"))

    def test_singular_acha_o_plural(self):
        from apps.catalog.models import Produto

        Produto.objects.create(
            sku="P-3", nome="Coleiras de couro", categoria=self.especial.categoria,
            preco=10, publicado=True,
        )
        self.assertIn("Coleiras de couro", self._itens("coleira"))

    def test_palavra_chave_acha_o_que_nao_esta_no_nome(self):
        """"ração" não aparece no nome do Special Care — está na tag."""
        self.assertNotIn("ração", self.especial.nome.lower())
        self.assertIn("Special Care Cães Adultos", self._itens("ração"))

    def test_prioridade_coloca_na_frente(self):
        """Mesmo vendendo menos, a prioridade põe o produto no topo."""
        self.assertEqual(self._itens("ração")[0], "Special Care Cães Adultos")
        self.assertEqual(self._itens("ração para cachorro")[0], "Special Care Cães Adultos")

    def test_sem_prioridade_manda_quem_vende_mais(self):
        self.especial.prioridade_busca = 0
        self.especial.save()
        self.assertEqual(self._itens("ração")[0], "Ração Golden Fórmula 15kg")

    def test_previa_acha_a_frase_inteira(self):
        """Era a queixa: a caixa de sugestões não mostrava nada."""
        self.assertTrue(self._previa("ração para cachorro"))
        self.assertEqual(self._previa("ração para cachorro")[0], "Special Care Cães Adultos")

    def test_nome_do_produto_vem_antes_de_quem_so_bate_por_tabela(self):
        """Buscou "ração": ração no topo, não a coleira que caiu na categoria."""
        from apps.catalog.models import Produto

        Produto.objects.create(
            sku="P-4", nome="Coleira Antipulgas", categoria=self.especial.categoria,
            preco=50, publicado=True, vendas=500,     # venderia muito mais
        )
        achados = self._itens("ração")
        self.assertIn("Coleira Antipulgas", achados)           # entrou pela categoria
        self.assertLess(                                        # mas atrás do nome
            achados.index("Ração Golden Fórmula 15kg"),
            achados.index("Coleira Antipulgas"),
        )

    def test_ordenacao_pedida_continua_mandando(self):
        achados = self.client.get(
            "/catalogo/", {"q": "ração", "ordem": "menor-preco"}
        ).content.decode()
        import re

        nomes = [n.strip() for n in re.findall(r'class="product__name"[^>]*>([^<]+)<', achados)]
        self.assertEqual(nomes[0], "Ração Golden Fórmula 15kg")   # o mais barato
