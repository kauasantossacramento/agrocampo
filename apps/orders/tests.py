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
            permite_assinatura=True, desconto_assinatura=10,
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


class AprovacaoTests(BasePedido):
    def _ate_analise(self, **kwargs):
        pedido = self._pedido(**kwargs)
        pedido.mudar_status(Pedido.Status.PAGO)
        pedido.mudar_status(Pedido.Status.AGUARDANDO_APROVACAO)
        return pedido

    def test_aprovacao_baixa_estoque_e_notifica(self):
        pedido = self._ate_analise(quantidade=2)
        aprovar_pedido(pedido, self.lojista)

        self.produto.refresh_from_db()
        pedido.refresh_from_db()

        self.assertEqual(self.produto.estoque, 3)
        self.assertEqual(self.produto.vendas, 2)
        self.assertEqual(pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertTrue(pedido.notificacoes.filter(tipo="pedido_aprovado").exists())

    def test_aprovacao_falha_se_o_estoque_sumiu(self):
        pedido = self._ate_analise(quantidade=3)
        self.produto.estoque = 1
        self.produto.save()

        with self.assertRaises(EstoqueInsuficiente):
            aprovar_pedido(pedido, self.lojista)

    def test_recusa_registra_motivo_e_notifica(self):
        pedido = self._ate_analise()
        recusar_pedido(pedido, self.lojista, "Sem estoque no depósito")
        pedido.refresh_from_db()

        self.assertEqual(pedido.status, Pedido.Status.RECUSADO)
        self.assertEqual(pedido.motivo_recusa, "Sem estoque no depósito")
        self.assertTrue(pedido.notificacoes.filter(tipo="pedido_recusado").exists())

    def test_aprovacao_de_item_recorrente_cria_assinatura(self):
        pedido = self._ate_analise(recorrente=True)
        aprovar_pedido(pedido, self.lojista)

        assinatura = Assinatura.objects.get(usuario=self.cliente)
        self.assertEqual(assinatura.produto, self.produto)
        self.assertEqual(assinatura.frequencia_dias, 30)
        self.assertEqual(assinatura.preco_unitario, Decimal("270.00"))

    def test_devolver_estoque_reverte_a_baixa(self):
        pedido = self._ate_analise(quantidade=2)
        aprovar_pedido(pedido, self.lojista)
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
