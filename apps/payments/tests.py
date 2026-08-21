"""Testes do gateway: cobrança, webhook e estorno."""
import hashlib
import hmac
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Categoria, Produto
from apps.orders.models import ItemPedido, Pedido
from apps.payments.gateways import get_gateway
from apps.payments.models import Estorno, Pagamento, ProvedorPagamento
from apps.payments.services import cobrar_cartao, cobrar_pix, estornar, processar_webhook, registrar_webhook

User = get_user_model()

CARTAO_APROVADO = {
    "numero": "4111111111111234",
    "nome": "MARIA SILVA",
    "validade_mes": 12,
    "validade_ano": 2030,
    "cvv": "123",
}
CARTAO_RECUSADO = {**CARTAO_APROVADO, "numero": "4111111111110000"}


class BaseCheckout(TestCase):
    def setUp(self):
        self.provedor = ProvedorPagamento.objects.create(
            nome="Stone", driver=ProvedorPagamento.Driver.SIMULADO, padrao=True, ativo=True,
            stone_webhook_secret="segredo-de-teste",
        )
        self.usuario = User.objects.create_user(
            email="maria@exemplo.com", password="senha-forte-123", first_name="Maria"
        )
        categoria = Categoria.objects.create(nome="Ração")
        self.produto = Produto.objects.create(
            sku="TEST-1", nome="Ração Teste 15kg", categoria=categoria,
            preco=Decimal("100.00"), estoque=10,
        )
        self.pedido = Pedido.objects.create(
            usuario=self.usuario, status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            nome_cliente="Maria Silva", email_cliente="maria@exemplo.com",
        )
        ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, nome_produto=self.produto.nome,
            quantidade=1, preco_unitario=Decimal("100.00"), preco_cheio=Decimal("100.00"),
        )
        self.pedido.recalcular()


class CobrancaCartaoTests(BaseCheckout):
    def test_cartao_aprovado_move_pedido_para_analise(self):
        pagamento = cobrar_cartao(self.pedido, CARTAO_APROVADO)
        self.pedido.refresh_from_db()

        self.assertEqual(pagamento.status, Pagamento.Status.PAGO)
        self.assertEqual(pagamento.valor_capturado, self.pedido.total)
        self.assertEqual(self.pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)

    def test_cartao_recusado_nao_avanca_o_pedido(self):
        pagamento = cobrar_cartao(self.pedido, CARTAO_RECUSADO)
        self.pedido.refresh_from_db()

        self.assertEqual(pagamento.status, Pagamento.Status.RECUSADO)
        self.assertEqual(self.pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)

    def test_pan_e_cvv_nunca_sao_persistidos(self):
        pagamento = cobrar_cartao(self.pedido, CARTAO_APROVADO)
        bruto = json.dumps([t.requisicao for t in pagamento.transacoes.all()])

        self.assertNotIn(CARTAO_APROVADO["numero"], bruto)
        self.assertNotIn("123", pagamento.transacoes.first().requisicao.get("cvv", ""))
        self.assertEqual(pagamento.ultimos_digitos, "1234")


class CobrancaPixTests(BaseCheckout):
    def test_pix_gera_brcode_e_fica_pendente(self):
        pagamento = cobrar_pix(self.pedido)

        self.assertEqual(pagamento.status, Pagamento.Status.PENDENTE)
        self.assertTrue(pagamento.pix_qrcode.startswith("0002"))
        self.assertIn("br.gov.bcb.pix", pagamento.pix_qrcode)
        self.assertIsNotNone(pagamento.pix_expira_em)


class WebhookTests(BaseCheckout):
    def _assinar(self, corpo: bytes) -> str:
        return hmac.new(b"segredo-de-teste", corpo, hashlib.sha256).hexdigest()

    def test_webhook_confirma_pagamento_e_avanca_pedido(self):
        pagamento = cobrar_pix(self.pedido)
        payload = {
            "type": "charge.paid",
            "data": {"id": pagamento.referencia_externa, "status": "paid", "amount": 10000},
        }
        corpo = json.dumps(payload).encode()

        evento = registrar_webhook(corpo, payload, self._assinar(corpo))
        self.assertTrue(evento.assinatura_valida)

        processar_webhook(evento)
        pagamento.refresh_from_db()
        self.pedido.refresh_from_db()

        self.assertEqual(pagamento.status, Pagamento.Status.PAGO)
        self.assertEqual(self.pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)

    def test_assinatura_invalida_e_rejeitada_na_view(self):
        payload = {"type": "charge.paid", "data": {"id": "x", "status": "paid"}}
        resposta = self.client.post(
            reverse("payments:webhook"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_STONE_SIGNATURE="assinatura-errada",
        )
        self.assertEqual(resposta.status_code, 401)

    def test_webhook_e_persistido_antes_de_processar(self):
        payload = {"type": "charge.paid", "data": {"id": "inexistente", "status": "paid"}}
        corpo = json.dumps(payload).encode()
        evento = registrar_webhook(corpo, payload, self._assinar(corpo))

        processar_webhook(evento)
        evento.refresh_from_db()

        self.assertTrue(evento.processado)
        self.assertIn("não encontrado", evento.erro)


class EstornoTests(BaseCheckout):
    def test_estorno_integral_marca_pagamento_como_estornado(self):
        pagamento = cobrar_cartao(self.pedido, CARTAO_APROVADO)
        estorno = estornar(pagamento, motivo=Estorno.Motivo.SEM_ESTOQUE)
        pagamento.refresh_from_db()

        self.assertEqual(estorno.status, Estorno.Status.CONCLUIDO)
        self.assertEqual(pagamento.status, Pagamento.Status.ESTORNADO)
        self.assertEqual(pagamento.valor_estornado, pagamento.valor)

    def test_estorno_parcial_mantem_saldo_estornavel(self):
        pagamento = cobrar_cartao(self.pedido, CARTAO_APROVADO)
        estornar(pagamento, valor=Decimal("40.00"))
        pagamento.refresh_from_db()

        self.assertEqual(pagamento.status, Pagamento.Status.ESTORNO_PARCIAL)
        self.assertEqual(pagamento.valor_estornavel, Decimal("60.00"))


class ProvedorTests(TestCase):
    def test_driver_cai_para_simulado_sem_credenciais(self):
        provedor = ProvedorPagamento.objects.create(
            nome="Stone", driver=ProvedorPagamento.Driver.STONE, padrao=True
        )
        self.assertFalse(provedor.credenciais_completas)
        self.assertEqual(get_gateway(provedor).codigo, "simulado")

    def test_driver_stone_ativa_com_credenciais_completas(self):
        provedor = ProvedorPagamento.objects.create(
            nome="Stone", driver=ProvedorPagamento.Driver.STONE, padrao=True,
            stone_api_key="chave", stone_merchant_id="merchant-1",
        )
        self.assertTrue(provedor.credenciais_completas)
        self.assertEqual(get_gateway(provedor).codigo, "stone")

    def test_parcelamento_respeita_valor_minimo_da_parcela(self):
        provedor = ProvedorPagamento.objects.create(
            nome="Stone", parcelas_maximas=12, valor_minimo_parcela=Decimal("30.00")
        )
        opcoes = provedor.parcelas_disponiveis(Decimal("100.00"))

        self.assertEqual(len(opcoes), 3)  # 1x, 2x (50), 3x (33,33)
        self.assertEqual(opcoes[-1]["valor"], Decimal("33.33"))

    def test_apenas_um_provedor_padrao(self):
        primeiro = ProvedorPagamento.objects.create(nome="A", padrao=True)
        ProvedorPagamento.objects.create(nome="B", padrao=True)
        primeiro.refresh_from_db()
        self.assertFalse(primeiro.padrao)
