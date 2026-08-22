"""Testes do ciclo de vida do pedido e do preço de assinatura."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.cart.models import Carrinho
from apps.catalog.models import Categoria, Produto
from apps.orders.models import Pedido
from apps.orders.services import (
    EstoqueInsuficiente,
    aprovar_pedido,
    separar_pedido,
    criar_pedido_do_carrinho,
    devolver_estoque,
    recusar_pedido,
)
from apps.subscriptions.models import Assinatura

User = get_user_model()


class BasePedido(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(
            email="joao@exemplo.com", password="senha-forte-123", first_name="João"
        )
        self.lojista = User.objects.create_user(
            email="lojista@agrocampo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )
        self.cliente.enderecos.create(
            apelido="Sítio", destinatario="João Pereira", cep="17300-000",
            logradouro="Estrada Vicinal", numero="s/n", bairro="Zona Rural",
            cidade="Dois Córregos", uf="SP", zona_rural=True, padrao=True,
        )
        categoria = Categoria.objects.create(nome="Ração")
        self.produto = Produto.objects.create(
            sku="P-1", nome="Ração Golden 15kg", categoria=categoria,
            preco=Decimal("300.00"), estoque=5,
            permite_assinatura=True, desconto_assinatura_proprio=10,
        )
        self.carrinho = Carrinho.objects.create(usuario=self.cliente)

    def _pedido(self, quantidade=1, recorrente=False):
        self.carrinho.adicionar(self.produto, quantidade, recorrente, 30 if recorrente else None)
        return criar_pedido_do_carrinho(self.carrinho, self.cliente)


class PrecoAssinaturaTests(BasePedido):
    def test_desconto_de_assinatura_aplicado_no_preco(self):
        self.assertEqual(self.produto.preco_assinatura, Decimal("270.00"))
        self.assertEqual(self.produto.economia_assinatura, Decimal("30.00"))

    def test_promocao_vigente_e_a_base_do_desconto_de_assinatura(self):
        self.produto.preco_promocional = Decimal("200.00")
        self.produto.save()
        self.assertEqual(self.produto.preco_atual, Decimal("200.00"))
        self.assertEqual(self.produto.preco_assinatura, Decimal("180.00"))

    def test_produto_sem_assinatura_ignora_o_desconto(self):
        self.produto.permite_assinatura = False
        self.produto.save()
        self.assertEqual(self.produto.preco_assinatura, self.produto.preco_atual)


class CriacaoPedidoTests(BasePedido):
    def test_pedido_congela_nome_e_preco_do_produto(self):
        pedido = self._pedido()
        item = pedido.itens.first()

        self.produto.nome = "Nome alterado depois da compra"
        self.produto.preco = Decimal("999.00")
        self.produto.save()
        item.refresh_from_db()

        self.assertEqual(item.nome_produto, "Ração Golden 15kg")
        self.assertEqual(item.preco_unitario, Decimal("300.00"))

    def test_item_recorrente_usa_preco_de_assinatura(self):
        pedido = self._pedido(recorrente=True)
        item = pedido.itens.first()

        self.assertTrue(item.recorrente)
        self.assertEqual(item.preco_unitario, Decimal("270.00"))
        self.assertEqual(pedido.desconto_assinatura, Decimal("30.00"))

    def test_carrinho_com_estoque_insuficiente_e_rejeitado(self):
        self.carrinho.adicionar(self.produto, 99)
        with self.assertRaises(EstoqueInsuficiente):
            criar_pedido_do_carrinho(self.carrinho, self.cliente)

    def test_criacao_registra_evento_na_timeline(self):
        pedido = self._pedido()
        self.assertEqual(pedido.eventos.count(), 1)
        self.assertEqual(pedido.eventos.first().titulo, "Pedido criado")


class MaquinaDeEstadosTests(BasePedido):
    def test_transicao_invalida_levanta_erro(self):
        pedido = self._pedido()
        with self.assertRaises(ValueError):
            pedido.mudar_status(Pedido.Status.ENTREGUE)

    def test_transicao_valida_grava_evento(self):
        pedido = self._pedido()
        pedido.mudar_status(Pedido.Status.PAGO, titulo="Pagamento confirmado")

        self.assertEqual(pedido.status, Pedido.Status.PAGO)
        self.assertIsNotNone(pedido.pago_em)
        self.assertEqual(pedido.eventos.last().titulo, "Pagamento confirmado")

    def test_forcar_ignora_a_maquina_de_estados(self):
        pedido = self._pedido()
        pedido.mudar_status(Pedido.Status.ENTREGUE, forcar=True)
        self.assertEqual(pedido.status, Pedido.Status.ENTREGUE)


class SeparacaoTests(BasePedido):
    """A etapa de aprovação foi removida: pago já entra em separação."""

    def _pago(self, **kwargs):
        pedido = self._pedido(**kwargs)
        pedido.mudar_status(Pedido.Status.PAGO)
        return pedido

    def test_separacao_baixa_estoque_e_notifica(self):
        pedido = self._pago(quantidade=2)
        separar_pedido(pedido)

        self.produto.refresh_from_db()
        pedido.refresh_from_db()

        self.assertEqual(self.produto.estoque, 3)
        self.assertEqual(self.produto.vendas, 2)
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertFalse(pedido.contato_pendente)
        self.assertTrue(pedido.notificacoes.filter(tipo="pedido_aprovado").exists())

    def test_sem_estoque_o_pedido_segue_e_marca_contato(self):
        """Faltando item, a compra não trava: um atendente liga para o cliente."""
        pedido = self._pago(quantidade=3)
        self.produto.estoque = 1
        self.produto.save()

        separar_pedido(pedido)
        pedido.refresh_from_db()
        self.produto.refresh_from_db()

        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertTrue(pedido.contato_pendente)
        self.assertIn(self.produto.nome, pedido.itens_em_falta)
        # baixou só o que existia — estoque negativo mentiria para o lojista
        self.assertEqual(self.produto.estoque, 0)
        self.assertFalse(pedido.itens.first().baixado_do_estoque)

    def test_pago_nao_passa_mais_por_aprovacao(self):
        pedido = self._pago()
        self.assertFalse(pedido.pode_ir_para(Pedido.Status.AGUARDANDO_APROVACAO))
        self.assertTrue(pedido.pode_ir_para(Pedido.Status.EM_SEPARACAO))

    def test_pedido_antigo_parado_na_fila_ainda_e_liberado(self):
        pedido = self._pago()
        pedido.mudar_status(Pedido.Status.AGUARDANDO_APROVACAO, forcar=True)
        aprovar_pedido(pedido, self.lojista)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)

    def test_recusa_registra_motivo_e_notifica(self):
        pedido = self._pago()
        pedido.mudar_status(Pedido.Status.AGUARDANDO_APROVACAO, forcar=True)
        recusar_pedido(pedido, self.lojista, "Sem estoque no depósito")
        pedido.refresh_from_db()

        self.assertEqual(pedido.status, Pedido.Status.RECUSADO)
        self.assertEqual(pedido.motivo_recusa, "Sem estoque no depósito")
        self.assertTrue(pedido.notificacoes.filter(tipo="pedido_recusado").exists())

    def test_item_recorrente_cria_assinatura(self):
        pedido = self._pago(recorrente=True)
        separar_pedido(pedido)

        assinatura = Assinatura.objects.get(usuario=self.cliente)
        self.assertEqual(assinatura.produto, self.produto)
        self.assertEqual(assinatura.frequencia_dias, 30)
        self.assertEqual(assinatura.preco_unitario, Decimal("270.00"))

    def test_devolver_estoque_reverte_a_baixa(self):
        pedido = self._pago(quantidade=2)
        separar_pedido(pedido)
        devolver_estoque(pedido)

        self.produto.refresh_from_db()
        self.assertEqual(self.produto.estoque, 5)


class CarrinhoTests(BasePedido):
    def test_frete_gratis_acima_do_limite(self):
        self.carrinho.adicionar(self.produto, 1)  # R$ 300 > R$ 199
        self.assertTrue(self.carrinho.frete_gratis)
        self.assertEqual(self.carrinho.frete, Decimal("0"))

    def test_mesclar_soma_quantidades_do_carrinho_anonimo(self):
        anonimo = Carrinho.objects.create(chave_sessao="sessao-abc")
        anonimo.adicionar(self.produto, 2)
        self.carrinho.adicionar(self.produto, 1)

        self.carrinho.mesclar(anonimo)

        self.assertEqual(self.carrinho.itens.count(), 1)
        self.assertEqual(self.carrinho.itens.first().quantidade, 3)
        self.assertFalse(Carrinho.objects.filter(pk=anonimo.pk).exists())


class DescontoAssinaturaGlobalTests(BasePedido):
    """O percentual vem da configuração da loja; o produto só sobrescreve."""

    def setUp(self):
        super().setUp()
        from apps.core.models import SiteConfig

        self.config = SiteConfig.load()

    def test_produto_sem_percentual_proprio_segue_o_global(self):
        self.produto.desconto_assinatura_proprio = None
        self.produto.save()

        self.config.desconto_assinatura_padrao = 25
        self.config.save()

        self.produto.refresh_from_db()
        self.assertEqual(self.produto.desconto_assinatura, 25)
        self.assertEqual(self.produto.preco_assinatura, Decimal("225.00"))
        self.assertTrue(self.produto.desconto_assinatura_e_global)

    def test_percentual_proprio_do_produto_vence_o_global(self):
        self.produto.desconto_assinatura_proprio = 5
        self.produto.save()

        self.config.desconto_assinatura_padrao = 25
        self.config.save()

        self.assertEqual(self.produto.desconto_assinatura, 5)
        self.assertEqual(self.produto.preco_assinatura, Decimal("285.00"))
        self.assertFalse(self.produto.desconto_assinatura_e_global)

    def test_mudar_o_global_muda_a_loja_toda_de_uma_vez(self):
        outro = Produto.objects.create(
            sku="P-2", nome="Outro assinável", categoria=self.produto.categoria,
            preco=Decimal("100.00"), estoque=5, permite_assinatura=True,
        )
        self.produto.desconto_assinatura_proprio = None
        self.produto.save()

        self.config.desconto_assinatura_padrao = 20
        self.config.save()

        self.produto.refresh_from_db()
        outro.refresh_from_db()
        self.assertEqual(self.produto.preco_assinatura, Decimal("240.00"))
        self.assertEqual(outro.preco_assinatura, Decimal("80.00"))


class AvaliacaoSomenteDeCompradorTests(BasePedido):
    def _rota(self):
        from django.urls import reverse

        return reverse("catalog:avaliar", args=[self.produto.slug])

    def test_quem_nunca_comprou_nao_avalia(self):
        from apps.catalog.models import Avaliacao

        self.client.force_login(self.cliente)
        self.client.post(self._rota(), {"nota": 5, "comentario": "ótimo"})

        self.assertFalse(Avaliacao.objects.filter(produto=self.produto).exists())
        self.assertFalse(self.produto.foi_comprado_por(self.cliente))

    def test_pedido_so_pago_ainda_nao_libera(self):
        """Pagou mas ainda não saiu para separação: pode nem ser entregue."""
        pedido = self._pedido()
        pedido.mudar_status(Pedido.Status.PAGO)
        self.assertFalse(self.produto.foi_comprado_por(self.cliente))

    def test_comprador_com_pedido_em_separacao_avalia(self):
        from apps.catalog.models import Avaliacao

        pedido = self._pedido()
        pedido.mudar_status(Pedido.Status.PAGO)
        separar_pedido(pedido)

        self.assertTrue(self.produto.foi_comprado_por(self.cliente))

        self.client.force_login(self.cliente)
        self.client.post(self._rota(), {"nota": 5, "comentario": "chegou rápido"})

        avaliacao = Avaliacao.objects.get(produto=self.produto, autor=self.cliente)
        self.assertEqual(avaliacao.nota, 5)
        self.assertTrue(avaliacao.compra_verificada)


class AnosDeMercadoTests(TestCase):
    def test_calculado_a_partir_da_fundacao(self):
        from django.utils import timezone

        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        config.ano_fundacao = 2012
        config.save()

        esperado = timezone.localdate().year - 2012
        self.assertEqual(config.anos_de_mercado, esperado)

    def test_fundacao_no_futuro_nao_vira_numero_negativo(self):
        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        config.ano_fundacao = 2999
        config.save()
        self.assertEqual(config.anos_de_mercado, 0)


class BlogDesligavelTests(TestCase):
    def test_desligado_o_blog_responde_404(self):
        from django.urls import reverse

        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        config.blog_ativo = False
        config.save()

        self.assertEqual(self.client.get(reverse("blog:lista")).status_code, 404)
        # e some do menu
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn(reverse("blog:lista"), html)

    def test_ligado_o_blog_responde(self):
        from django.urls import reverse

        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        config.blog_ativo = True
        config.save()
        self.assertEqual(self.client.get(reverse("blog:lista")).status_code, 200)


class RegrasComerciaisEditaveisTests(BasePedido):
    """As promessas da vitrine têm que sair da configuração — e ser cumpridas."""

    def setUp(self):
        super().setUp()
        from apps.core.models import SiteConfig

        self.config = SiteConfig.load()

    def test_valor_do_frete_vem_da_configuracao(self):
        """Regressão: R$ 24,90 estava fixo no código, sem jeito de mudar."""
        self.config.frete_valor = Decimal("35.00")
        self.config.frete_gratis_acima_de = Decimal("1000.00")
        self.config.save()

        self.carrinho.adicionar(self.produto, 1)   # R$ 300, abaixo do mínimo
        self.assertEqual(self.carrinho.frete, Decimal("35.00"))

    def test_frete_gratis_acima_do_limite_configurado(self):
        self.config.frete_valor = Decimal("35.00")
        self.config.frete_gratis_acima_de = Decimal("200.00")
        self.config.save()

        self.carrinho.adicionar(self.produto, 1)   # R$ 300 > R$ 200
        self.assertEqual(self.carrinho.frete, Decimal("0"))

    def test_limite_zero_desliga_o_frete_gratis(self):
        """Sem a guarda, um carrinho de R$ 0,01 já sairia com frete grátis."""
        self.config.frete_valor = Decimal("35.00")
        self.config.frete_gratis_acima_de = Decimal("0")
        self.config.save()

        self.carrinho.adicionar(self.produto, 1)
        self.assertEqual(self.carrinho.frete, Decimal("35.00"))

    def test_desconto_pix_prometido_e_realmente_abatido(self):
        """Regressão: a vitrine anunciava 5% no Pix e cobrava o total cheio."""
        from apps.payments.services import cobrar_pix

        self.config.desconto_pix = 10
        self.config.frete_gratis_acima_de = Decimal("100.00")
        self.config.save()

        pedido = self._pedido()
        total_cheio = pedido.total

        pagamento = cobrar_pix(pedido)
        pedido.refresh_from_db()

        self.assertEqual(pedido.desconto_pix, Decimal("30.00"))
        self.assertEqual(pedido.total, total_cheio - Decimal("30.00"))
        self.assertEqual(pagamento.valor, pedido.total)

    def test_trocar_pix_por_cartao_desfaz_o_abatimento(self):
        from apps.payments.services import cobrar_cartao, cobrar_pix

        self.config.desconto_pix = 10
        self.config.frete_gratis_acima_de = Decimal("100.00")
        self.config.save()

        pedido = self._pedido()
        total_cheio = pedido.total

        cobrar_pix(pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.desconto_pix, Decimal("30.00"))

        cobrar_cartao(pedido, {
            "numero": "4111111111111234", "nome": "JOAO",
            "validade_mes": 12, "validade_ano": 2030, "cvv": "123",
        })
        pedido.refresh_from_db()

        self.assertEqual(pedido.desconto_pix, Decimal("0"))
        self.assertEqual(pedido.total, total_cheio)

    def test_desconto_pix_zerado_nao_abate_nada(self):
        from apps.payments.services import cobrar_pix

        self.config.desconto_pix = 0
        self.config.save()

        pedido = self._pedido()
        total_cheio = pedido.total
        cobrar_pix(pedido)
        pedido.refresh_from_db()

        self.assertEqual(pedido.desconto_pix, Decimal("0"))
        self.assertEqual(pedido.total, total_cheio)


class DiferenciaisRemoviveisTests(TestCase):
    def test_apagar_todos_remove_a_faixa_da_home(self):
        """Regressão: havia quatro promessas fixas no {% empty %} do template.
        Apagar tudo pelo admin fazia elas reaparecerem — o lojista não
        conseguia remover uma promessa que não pudesse cumprir."""
        from django.urls import reverse

        from apps.core.models import Diferencial

        Diferencial.objects.create(titulo="Entrega em toda a região", icone="caminhao")
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("Entrega em toda a região", html)

        Diferencial.objects.all().delete()
        html = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn("Entregamos onde outros não chegam", html)
        self.assertNotIn("Compra 100% garantida", html)


class QuantidadeNoCarrinhoTests(BasePedido):
    """Regressão: os três campos do seletor chamavam-se `quantidade`.

    O navegador enviava o valor do botão E o do input; `POST.get()` devolve o
    último da ordem do documento. Como o "−" vem antes do input, ele nunca
    surtia efeito — só o "+" funcionava.
    """

    def _rota(self, item):
        from django.urls import reverse

        return reverse("cart:atualizar", args=[item.id])

    def setUp(self):
        super().setUp()
        self.client.force_login(self.cliente)
        # o carrinho da sessão do client precisa ser o mesmo do usuário
        self.item = self.carrinho.adicionar(self.produto, 3)

    def test_botao_de_diminuir_reduz_uma_unidade(self):
        self.client.post(self._rota(self.item), {"ajuste": "-1", "quantidade": "3"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade, 2)

    def test_botao_de_aumentar_soma_uma_unidade(self):
        self.client.post(self._rota(self.item), {"ajuste": "1", "quantidade": "3"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade, 4)

    def test_diminuir_ate_zero_remove_o_item(self):
        self.item.quantidade = 1
        self.item.save(update_fields=["quantidade"])

        self.client.post(self._rota(self.item), {"ajuste": "-1", "quantidade": "1"})
        self.assertFalse(
            self.carrinho.itens.filter(pk=self.item.pk).exists(),
            "chegar a zero tem que tirar o item do carrinho",
        )

    def test_digitar_a_quantidade_continua_funcionando(self):
        self.client.post(self._rota(self.item), {"quantidade": "5"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade, 5)

    def test_ajuste_parte_do_banco_e_nao_do_campo_enviado(self):
        """Dois cliques seguidos não podem se anular por valor desatualizado."""
        self.client.post(self._rota(self.item), {"ajuste": "-1", "quantidade": "3"})
        self.client.post(self._rota(self.item), {"ajuste": "-1", "quantidade": "3"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade, 1)

    def test_nao_passa_do_estoque(self):
        self.item.quantidade = self.produto.estoque
        self.item.save(update_fields=["quantidade"])

        self.client.post(self._rota(self.item), {"ajuste": "1"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade, self.produto.estoque)


class IconeDeCategoriaTests(TestCase):
    """Regressão: a migration trocou o significado do campo mas não os dados.

    Bases já existentes ficaram com `🐕` gravado; o template montava
    `href="#c-🐕"`, o símbolo não existia e o ícone sumia sem erro nenhum.
    """

    def test_emoji_antigo_nao_gera_referencia_quebrada(self):
        from apps.catalog.models import Categoria

        categoria = Categoria.objects.create(nome="Herdada", icone="🐕")
        self.assertEqual(categoria.icone_svg, "pata")

    def test_icone_vazio_cai_no_generico(self):
        from apps.catalog.models import Categoria

        categoria = Categoria.objects.create(nome="Sem ícone", icone="")
        self.assertEqual(categoria.icone_svg, "pata")

    def test_chave_valida_e_preservada(self):
        from apps.catalog.models import Categoria

        categoria = Categoria.objects.create(nome="Ração", icone="racao")
        self.assertEqual(categoria.icone_svg, "racao")

    def test_home_so_referencia_simbolos_que_existem(self):
        """Cada href="#c-x" da home precisa ter um <symbol id="c-x">."""
        import re

        from django.core.management import call_command
        from django.urls import reverse

        call_command("seed", verbosity=0)
        html = self.client.get(reverse("core:home")).content.decode()

        usados = set(re.findall(r'href="#(c-[^"]+)"', html))
        definidos = set(re.findall(r'<symbol id="(c-[^"]+)"', html))

        self.assertTrue(usados, "a home deveria usar ícones de categoria")
        faltando = usados - definidos
        self.assertFalse(faltando, f"ícones referenciados sem <symbol>: {faltando}")


class VariacaoTests(BasePedido):
    """Um mesmo produto vendido em 2kg, 5kg e 15kg."""

    def setUp(self):
        super().setUp()
        from apps.catalog.models import VariacaoProduto

        self.dois = VariacaoProduto.objects.create(
            produto=self.produto, quantidade=Decimal("2"), unidade="kg",
            preco=Decimal("60.00"), estoque=10, padrao=True,
        )
        self.cinco = VariacaoProduto.objects.create(
            produto=self.produto, quantidade=Decimal("5"), unidade="kg",
            preco=Decimal("130.00"), estoque=4,
        )

    def test_rotulo_sem_zeros_sobrando(self):
        self.assertEqual(self.dois.rotulo, "2kg")
        self.assertEqual(self.cinco.rotulo, "5kg")

    def test_preco_do_produto_segue_a_variacao_padrao(self):
        self.assertEqual(self.produto.preco_atual, Decimal("60.00"))
        self.assertEqual(self.produto.preco_a_partir_de, Decimal("60.00"))

    def test_estoque_total_soma_as_variacoes(self):
        self.assertEqual(self.produto.estoque_total, 14)

    def test_tamanhos_diferentes_sao_linhas_diferentes_no_carrinho(self):
        self.carrinho.adicionar(self.produto, 1, variacao=self.dois)
        self.carrinho.adicionar(self.produto, 1, variacao=self.cinco)
        self.assertEqual(self.carrinho.itens.count(), 2)

    def test_o_mesmo_tamanho_soma_na_mesma_linha(self):
        self.carrinho.adicionar(self.produto, 1, variacao=self.dois)
        self.carrinho.adicionar(self.produto, 2, variacao=self.dois)
        self.assertEqual(self.carrinho.itens.count(), 1)
        self.assertEqual(self.carrinho.itens.first().quantidade, 3)

    def test_sem_variacao_informada_usa_a_padrao(self):
        self.carrinho.adicionar(self.produto, 1)
        self.assertEqual(self.carrinho.itens.first().variacao, self.dois)

    def test_pedido_congela_o_rotulo_do_tamanho(self):
        self.carrinho.adicionar(self.produto, 1, variacao=self.cinco)
        pedido = criar_pedido_do_carrinho(self.carrinho, self.cliente)
        item = pedido.itens.first()

        self.assertEqual(item.variacao_rotulo, "5kg")
        self.assertEqual(item.preco_unitario, Decimal("130.00"))
        self.assertIn("5kg", item.descricao_completa)

    def test_separacao_baixa_o_estoque_da_variacao_certa(self):
        self.carrinho.adicionar(self.produto, 2, variacao=self.cinco)
        pedido = criar_pedido_do_carrinho(self.carrinho, self.cliente)
        pedido.mudar_status(Pedido.Status.PAGO)
        separar_pedido(pedido)

        self.cinco.refresh_from_db()
        self.dois.refresh_from_db()
        self.assertEqual(self.cinco.estoque, 2)
        self.assertEqual(self.dois.estoque, 10)

    def test_carrinho_recusa_mais_do_que_o_tamanho_tem(self):
        self.carrinho.adicionar(self.produto, 4, variacao=self.cinco)
        item = self.carrinho.itens.first()
        item.quantidade = 5
        self.assertFalse(item.disponivel)


class LinhaTests(BasePedido):
    def test_filtro_por_linha(self):
        from apps.catalog.models import Produto as P

        self.produto.linha = P.Linha.OURO
        self.produto.save()
        outro = P.objects.create(
            sku="P-2", nome="Ração Comum", categoria=self.produto.categoria,
            preco=Decimal("80.00"), estoque=3, linha=P.Linha.BRONZE,
        )
        self.assertIn(self.produto, P.objects.da_linha(P.Linha.OURO))
        self.assertNotIn(outro, P.objects.da_linha(P.Linha.OURO))

    def test_produto_sem_linha_nao_entra_em_nenhuma_vitrine(self):
        from apps.catalog.models import Produto as P

        self.assertEqual(self.produto.linha, "")
        for valor, _ in P.Linha.choices:
            self.assertNotIn(self.produto, P.objects.da_linha(valor))


class ContatoPorWhatsAppTests(BasePedido):
    """Quando falta item, o painel precisa dar um caminho até o cliente."""

    def _pedido_com_falta(self):
        self.carrinho.adicionar(self.produto, 3)
        pedido = criar_pedido_do_carrinho(self.carrinho, self.cliente)
        pedido.mudar_status(Pedido.Status.PAGO)
        self.produto.estoque = 1
        self.produto.save()
        separar_pedido(pedido)
        pedido.refresh_from_db()
        return pedido

    def test_link_traz_o_numero_do_pedido_e_o_que_faltou(self):
        from apps.dashboard.views import _whatsapp_do_pedido

        self.cliente.telefone = "(75) 98888-7777"
        self.cliente.aceita_contato_whatsapp = True
        self.cliente.save()

        pedido = self._pedido_com_falta()
        link = _whatsapp_do_pedido(pedido)

        self.assertIn("wa.me/5575988887777", link)
        self.assertIn(pedido.numero, link.replace("%20", " "))

    def test_sem_autorizacao_nao_ha_link(self):
        from apps.dashboard.views import _whatsapp_do_pedido

        self.cliente.telefone = "(75) 98888-7777"
        self.cliente.aceita_contato_whatsapp = False
        self.cliente.save()

        self.assertEqual(_whatsapp_do_pedido(self._pedido_com_falta()), "")

    def test_tela_do_pedido_oferece_o_email_quando_nao_ha_whatsapp(self):
        pedido = self._pedido_com_falta()
        self.client.force_login(self.lojista)
        resposta = self.client.get(f"/painel/pedidos/{pedido.numero}/")

        self.assertContains(resposta, "Falar com o cliente")
        self.assertContains(resposta, pedido.email_cliente)


class PrecoComVariacaoTests(BasePedido):
    """A vitrine não pode estampar desconto que o preço não dá."""

    def setUp(self):
        super().setUp()
        from apps.catalog.models import VariacaoProduto

        # o produto tem promoção própria, mas quem manda no preço é a variação
        self.produto.preco_promocional = Decimal("270.00")
        self.produto.save()
        self.var = VariacaoProduto.objects.create(
            produto=self.produto, quantidade=Decimal("15"), unidade="kg",
            preco=Decimal("300.00"), estoque=5, padrao=True,
        )

    def test_promocao_do_produto_nao_vale_quando_ha_variacao(self):
        self.assertFalse(self.produto.promocao_vigente)
        self.assertEqual(self.produto.percentual_desconto, 0)
        self.assertEqual(self.produto.preco_cheio, Decimal("300.00"))
        self.assertEqual(self.produto.preco_atual, Decimal("300.00"))

    def test_promocao_da_variacao_aparece_no_card(self):
        self.var.preco_promocional = Decimal("240.00")
        self.var.save()

        self.assertTrue(self.produto.promocao_vigente)
        self.assertEqual(self.produto.preco_atual, Decimal("240.00"))
        self.assertEqual(self.produto.percentual_desconto, 20)

    def test_assinatura_segue_o_preco_da_variacao(self):
        self.assertEqual(self.var.preco_assinatura, Decimal("270.00"))
        self.assertEqual(self.var.economia_assinatura, Decimal("30.00"))
