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


def _cartao(**extra):
    """DadosCartao de teste, para os drivers que falam com a API de verdade."""
    from apps.payments.gateways.base import DadosCartao

    return DadosCartao(**{**CARTAO_APROVADO, **extra})


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
    def test_cartao_aprovado_manda_pedido_para_separacao(self):
        pagamento = cobrar_cartao(self.pedido, CARTAO_APROVADO)
        self.pedido.refresh_from_db()

        self.assertEqual(pagamento.status, Pagamento.Status.PAGO)
        self.assertEqual(pagamento.valor_capturado, self.pedido.total)
        self.assertEqual(self.pedido.status, Pedido.Status.EM_SEPARACAO)

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
        self.assertEqual(self.pedido.status, Pedido.Status.EM_SEPARACAO)

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


class PagarmeTests(BaseCheckout):
    """Driver da Pagar.me: o que a loja manda e o que entende de volta.

    A API não é chamada de verdade — as respostas são as que a documentação
    descreve. O que se verifica aqui é a tradução: valores em centavos,
    autenticação Basic, a cobrança certa dentro do pedido e os dois níveis
    de status virando o status da loja.
    """

    def setUp(self):
        super().setUp()
        from apps.payments.gateways.pagarme import PagarmeGateway

        self.provedor.driver = ProvedorPagamento.Driver.PAGARME
        self.provedor.pagarme_secret_key_sandbox = "sk_test_chave"
        self.provedor.pagarme_public_key_sandbox = "pk_test_chave"
        self.provedor.pagarme_account_id = "acc_de_teste"
        self.provedor.save()
        self.gateway = PagarmeGateway(self.provedor)
        self.pagamento = Pagamento.objects.create(
            pedido=self.pedido, provedor=self.provedor,
            metodo=Pagamento.Metodo.CARTAO, valor=Decimal("100.00"),
        )

    def _resposta(self, corpo, status=200):
        """Finge uma resposta da Pagar.me, sem sair para a internet."""
        from unittest.mock import patch

        class Falsa:
            status_code = status

            def json(self):
                return corpo

        return patch("apps.payments.gateways.pagarme.requests.request", return_value=Falsa())

    @staticmethod
    def _pedido_pago(status_transacao="captured", status_cobranca="paid", extra=None):
        transacao = {
            "status": status_transacao, "success": True,
            "acquirer_tid": "tid-1", "acquirer_nsu": "nsu-1",
            "acquirer_auth_code": "auth-1",
            "card": {"brand": "visa", "last_four_digits": "1234"},
        }
        transacao.update(extra or {})
        return {
            "id": "or_abc", "status": status_cobranca, "amount": 10000,
            "charges": [{"id": "ch_abc", "status": status_cobranca,
                         "amount": 10000, "last_transaction": transacao}],
        }

    # ----------------------------------------------------------- escolha
    def test_driver_e_escolhido_quando_ha_chave(self):
        self.assertEqual(get_gateway(self.provedor).codigo, "pagarme")

    def test_sem_chave_cai_no_simulado(self):
        """Trocar o driver sem a chave não pode quebrar o checkout."""
        self.provedor.pagarme_secret_key_sandbox = ""
        self.provedor.save()
        self.assertEqual(get_gateway(self.provedor).codigo, "simulado")

    def test_ambiente_escolhe_a_chave(self):
        """Apontar para produção com chave de teste cobraria no lugar errado."""
        self.provedor.pagarme_secret_key_producao = "sk_producao"
        self.provedor.ambiente = ProvedorPagamento.Ambiente.PRODUCAO
        self.provedor.save()
        self.assertEqual(self.provedor.pagarme_secret_key, "sk_producao")
        self.provedor.ambiente = ProvedorPagamento.Ambiente.SANDBOX
        self.assertEqual(self.provedor.pagarme_secret_key, "sk_test_chave")

    # ------------------------------------------------------------ cartão
    def test_cartao_vai_em_centavos_e_com_basic(self):
        with self._resposta(self._pedido_pago(), 200) as chamada:
            resultado = self.gateway.autorizar_cartao(
                self.pagamento, _cartao(), parcelas=3
            )

        kwargs = chamada.call_args[1]
        corpo = json.loads(kwargs["data"])
        pagamento_enviado = corpo["payments"][0]
        self.assertEqual(kwargs["auth"], ("sk_test_chave", ""))
        self.assertEqual(pagamento_enviado["amount"], 10000)
        self.assertEqual(pagamento_enviado["credit_card"]["installments"], 3)
        self.assertEqual(corpo["items"][0]["amount"], 10000)
        self.assertEqual(corpo["code"], self.pedido.numero)
        self.assertEqual(resultado.status, Pagamento.Status.PAGO)
        self.assertEqual(resultado.referencia_externa, "ch_abc")
        self.assertEqual(resultado.ultimos_digitos, "1234")

    def test_captura_manual_so_autoriza(self):
        self.provedor.captura_automatica = False
        self.provedor.save()
        with self._resposta(
            self._pedido_pago("authorized_pending_capture", "pending")
        ) as chamada:
            resultado = self.gateway.autorizar_cartao(self.pagamento, _cartao())

        corpo = json.loads(chamada.call_args[1]["data"])
        self.assertEqual(
            corpo["payments"][0]["credit_card"]["operation_type"], "auth_only"
        )
        self.assertEqual(resultado.status, Pagamento.Status.AUTORIZADO)

    def test_cartao_recusado_nao_e_sucesso(self):
        """Recusa volta 200 com a transação reprovada — não é erro de HTTP."""
        corpo = self._pedido_pago(
            "not_authorized", "failed",
            extra={"success": False,
                   "gateway_response": {"errors": [{"message": "Cartão sem limite"}]}},
        )
        with self._resposta(corpo, 200):
            resultado = self.gateway.autorizar_cartao(self.pagamento, _cartao())

        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.status, Pagamento.Status.RECUSADO)
        self.assertIn("limite", resultado.mensagem)

    def test_numero_do_cartao_nao_vai_para_a_auditoria(self):
        """O PAN está dentro de duas listas e um dicionário no payload."""
        from apps.payments.models import TransacaoPagamento

        with self._resposta(self._pedido_pago()):
            self.gateway.autorizar_cartao(self.pagamento, _cartao())

        registro = TransacaoPagamento.objects.get(operacao="autorizacao")
        gravado = json.dumps(registro.requisicao)
        self.assertNotIn("4111111111111234", gravado)
        self.assertNotIn("111111111111", gravado)

    # --------------------------------------------------------------- pix
    def test_pix_devolve_copia_e_cola(self):
        corpo = self._pedido_pago(
            "waiting_payment", "pending",
            extra={"qr_code": "00020126BR.GOV.BCB.PIX",
                   "qr_code_url": "https://api.pagar.me/qr.png",
                   "expires_at": "2026-11-04T23:59:59Z"},
        )
        with self._resposta(corpo) as chamada:
            resultado = self.gateway.criar_pix(self.pagamento)

        enviado = json.loads(chamada.call_args[1]["data"])["payments"][0]
        self.assertEqual(enviado["payment_method"], "pix")
        self.assertEqual(enviado["pix"]["expires_in"], 30 * 60)
        self.assertEqual(resultado.pix_qrcode, "00020126BR.GOV.BCB.PIX")
        self.assertEqual(resultado.status, Pagamento.Status.PENDENTE)
        self.assertIsNotNone(resultado.pix_expira_em)

    # --------------------------------------------------- ciclo e estorno
    def test_estorno_parcial_manda_o_valor(self):
        self.pagamento.referencia_externa = "ch_abc"
        self.pagamento.save()
        with self._resposta(
            {"id": "ch_abc", "status": "paid",
             "last_transaction": {"status": "partial_refunded"}}
        ) as chamada:
            resultado = self.gateway.estornar(self.pagamento, Decimal("40.00"))

        metodo, url = chamada.call_args[0]
        self.assertEqual(metodo, "DELETE")
        self.assertTrue(url.endswith("/charges/ch_abc"))
        self.assertEqual(json.loads(chamada.call_args[1]["data"])["amount"], 4000)
        self.assertEqual(resultado.status, Pagamento.Status.ESTORNO_PARCIAL)

    def test_consulta_le_a_cobranca(self):
        self.pagamento.referencia_externa = "ch_abc"
        self.pagamento.save()
        with self._resposta(
            {"id": "ch_abc", "status": "paid", "last_transaction": {"status": "captured"}}
        ) as chamada:
            resultado = self.gateway.consultar(self.pagamento)

        self.assertEqual(chamada.call_args[0][0], "GET")
        self.assertEqual(resultado.status, Pagamento.Status.PAGO)

    # ----------------------------------------------------------- webhook
    def test_webhook_confirma_na_api_em_vez_de_acreditar(self):
        """O aviso diz que mudou; quem diz o que ficou é a consulta."""
        self.pagamento.referencia_externa = "ch_abc"
        self.pagamento.metodo = Pagamento.Metodo.PIX
        self.pagamento.save()

        aviso = {"type": "charge.paid",
                 "data": {"id": "ch_abc", "status": "paid", "amount": 10000}}
        confirmacao = {"id": "ch_abc", "status": "paid", "paid_amount": 10000,
                       "last_transaction": {"status": "captured",
                                            "end_to_end_id": "E123"}}
        with self._resposta(confirmacao) as chamada:
            dados = self.gateway.interpretar_webhook(aviso)

        self.assertEqual(chamada.call_args[0][0], "GET")
        self.assertEqual(dados["referencia_externa"], "ch_abc")
        self.assertEqual(dados["status"], Pagamento.Status.PAGO)
        self.assertEqual(dados["valor"], Decimal("100.00"))
        self.assertEqual(dados["e2e_id"], "E123")

    def test_webhook_sobrevive_a_api_fora_do_ar(self):
        """Sem resposta, o evento fica gravado para reprocessar — sem 500."""
        from unittest.mock import patch

        import requests as req

        with patch("apps.payments.gateways.pagarme.requests.request",
                   side_effect=req.RequestException("timeout")):
            dados = self.gateway.interpretar_webhook(
                {"type": "charge.paid", "data": {"id": "ch_abc"}}
            )
        self.assertEqual(dados["status"], "")
        self.assertEqual(dados["referencia_externa"], "ch_abc")

    def test_webhook_sem_basic_e_recusado_quando_ha_senha(self):
        self.provedor.pagarme_webhook_usuario = "loja"
        self.provedor.pagarme_webhook_senha = "segredo"
        self.provedor.save()

        resposta = self.client.post(
            reverse("payments:webhook_pagarme"),
            data=json.dumps({"type": "charge.paid", "data": {"id": "ch_abc"}}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 401)

    def test_webhook_com_basic_correto_entra(self):
        import base64

        self.provedor.pagarme_webhook_usuario = "loja"
        self.provedor.pagarme_webhook_senha = "segredo"
        self.provedor.save()
        credencial = base64.b64encode(b"loja:segredo").decode()

        with self._resposta({"id": "ch_abc", "status": "paid",
                             "last_transaction": {"status": "captured"}}):
            resposta = self.client.post(
                reverse("payments:webhook_pagarme"),
                data=json.dumps({"type": "charge.paid", "data": {"id": "ch_abc"}}),
                content_type="application/json",
                HTTP_AUTHORIZATION="Basic " + credencial,
            )
        self.assertEqual(resposta.status_code, 200)

    def test_webhook_sem_tipo_e_recusado(self):
        resposta = self.client.post(
            reverse("payments:webhook_pagarme"),
            data=json.dumps({"data": {"id": "ch_abc"}}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)


class CompraComPagarmeTests(BaseCheckout):
    """O que aconteceu na primeira compra real, em 04/11/2026.

    A Pagar.me recusou o Pix com "The customer Document is required.": o
    comprador não tinha CPF, que é opcional no cadastro. A tela ainda
    mostrou "Recusado" e, logo abaixo, "assim que confirmar esta página
    avança sozinha". E quem voltou ao carrinho o achou vazio, com os itens
    já dentro de um pedido que nada mostrava.
    """

    RECUSA_SEM_CPF = {
        "id": "or_x", "status": "failed",
        "charges": [{"id": "ch_x", "status": "failed", "last_transaction": {
            "status": "failed", "success": False,
            "gateway_response": {"code": "400", "errors": [
                {"message": "The customer Document is required."}]},
        }}],
    }

    def setUp(self):
        super().setUp()
        self.provedor.driver = ProvedorPagamento.Driver.PAGARME
        self.provedor.pagarme_secret_key_sandbox = "sk_test_chave"
        self.provedor.save()
        self.client.force_login(self.usuario)

    def _resposta(self, corpo, status=200):
        from unittest.mock import patch

        class Falsa:
            status_code = status

            def json(self):
                return corpo

        return patch("apps.payments.gateways.pagarme.requests.request", return_value=Falsa())

    # ------------------------------------------------------------- CPF
    def test_cpf_confere_os_digitos(self):
        from apps.core.documentos import cpf_valido, formatar_cpf

        self.assertTrue(cpf_valido("083.627.535-79"))
        self.assertTrue(cpf_valido("08362753579"))
        self.assertFalse(cpf_valido("083.627.535-70"))
        self.assertFalse(cpf_valido("111.111.111-11"))
        self.assertFalse(cpf_valido(""))
        self.assertEqual(formatar_cpf("08362753579"), "083.627.535-79")

    def test_checkout_pede_cpf_a_quem_nao_tem(self):
        html = self.client.get(
            reverse("payments:checkout", args=[self.pedido.numero])
        ).content.decode()
        self.assertIn('name="comprador_cpf"', html)

    def test_quem_ja_tem_cpf_nao_e_perguntado_de_novo(self):
        self.usuario.cpf = "083.627.535-79"
        self.usuario.save()
        html = self.client.get(
            reverse("payments:checkout", args=[self.pedido.numero])
        ).content.decode()
        self.assertNotIn('name="comprador_cpf"', html)

    def test_simulado_nao_pede_cpf(self):
        """Sem adquirente de verdade ninguém exige o documento."""
        self.provedor.driver = ProvedorPagamento.Driver.SIMULADO
        self.provedor.save()
        html = self.client.get(
            reverse("payments:checkout", args=[self.pedido.numero])
        ).content.decode()
        self.assertNotIn('name="comprador_cpf"', html)

    def test_cpf_invalido_nao_chega_ao_adquirente(self):
        from unittest.mock import patch

        with patch("apps.payments.gateways.pagarme.requests.request") as chamada:
            resposta = self.client.post(
                reverse("payments:checkout", args=[self.pedido.numero]),
                {"metodo": "pix", "comprador_cpf": "123.456.789-00"},
            )
        self.assertEqual(resposta.status_code, 302)
        chamada.assert_not_called()
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.cpf, "")

    def test_cpf_valido_fica_no_cadastro_e_vai_na_cobranca(self):
        aprovado = {
            "id": "or_y", "status": "pending",
            "charges": [{"id": "ch_y", "status": "pending", "last_transaction": {
                "status": "waiting_payment", "success": True,
                "qr_code": "00020126BR.GOV.BCB.PIX", "qr_code_url": "https://x/qr.png",
            }}],
        }
        with self._resposta(aprovado) as chamada:
            self.client.post(
                reverse("payments:checkout", args=[self.pedido.numero]),
                {"metodo": "pix", "comprador_cpf": "08362753579"},
            )
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.cpf, "083.627.535-79")
        enviado = json.loads(chamada.call_args[1]["data"])
        self.assertEqual(enviado["customer"]["document"], "08362753579")
        self.assertEqual(enviado["customer"]["document_type"], "CPF")

    # ------------------------------------------------- recusa do Pix
    def test_pix_recusado_fica_recusado_e_em_portugues(self):
        """Antes ficava "aguardando" esperando um QR Code que nunca viria."""
        self.usuario.cpf = "083.627.535-79"
        self.usuario.save()
        with self._resposta(self.RECUSA_SEM_CPF):
            pagamento = cobrar_pix(self.pedido)

        self.assertEqual(pagamento.status, Pagamento.Status.RECUSADO)
        self.assertIn("CPF", pagamento.mensagem)
        self.assertNotIn("required", pagamento.mensagem)

    def test_tela_do_pix_recusado_oferece_tentar_de_novo(self):
        self.usuario.cpf = "083.627.535-79"
        self.usuario.save()
        with self._resposta(self.RECUSA_SEM_CPF):
            pagamento = cobrar_pix(self.pedido)

        html = self.client.get(reverse("payments:pix", args=[pagamento.pk])).content.decode()
        self.assertIn("O Pix não foi gerado", html)
        self.assertIn("Tentar de novo", html)
        self.assertNotIn("avança sozinha", html)
        self.assertNotIn("Stone", html)

    def test_recusa_repetida_pelo_webhook_nao_manda_outro_aviso(self):
        """A recusa chega na resposta e de novo no webhook: um aviso só."""
        from apps.notifications.models import Notificacao

        pagamento = Pagamento.objects.create(
            pedido=self.pedido, provedor=self.provedor, metodo=Pagamento.Metodo.CARTAO,
            valor=Decimal("100.00"), referencia_externa="ch_x",
        )
        pagamento.marcar_recusado("O banco não aprovou o pagamento.")
        antes = Notificacao.objects.count()

        confirmacao = {"id": "ch_x", "status": "failed",
                       "last_transaction": {"status": "not_authorized"}}
        with self._resposta(confirmacao):
            evento = registrar_webhook(
                b"{}", {"type": "charge.payment_failed", "data": {"id": "ch_x"}}, ""
            )
            processar_webhook(evento)

        self.assertEqual(Notificacao.objects.count(), antes)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.mensagem, "O banco não aprovou o pagamento.")

    # ------------------------------------------- carrinho e o "voltar"
    def test_carrinho_mostra_o_pedido_esperando_pagamento(self):
        html = self.client.get(reverse("cart:detalhe")).content.decode()
        self.assertIn(f"Pedido {self.pedido.numero} esperando pagamento", html)
        self.assertIn(reverse("payments:checkout", args=[self.pedido.numero]), html)

    def test_tela_de_entrega_antiga_leva_ao_pedido_ja_fechado(self):
        """Confirmar de novo uma tela velha caía em "carrinho vazio"."""
        resposta = self.client.get(reverse("cart:checkout"))
        self.assertRedirects(
            resposta,
            reverse("payments:checkout", args=[self.pedido.numero]),
            fetch_redirect_response=False,
        )

    def test_pedido_antigo_nao_sequestra_compra_nova(self):
        """Meia hora depois, carrinho vazio é carrinho vazio."""
        from datetime import timedelta

        from django.utils import timezone

        Pedido.objects.filter(pk=self.pedido.pk).update(
            criado_em=timezone.now() - timedelta(hours=2)
        )
        resposta = self.client.get(reverse("cart:checkout"))
        self.assertRedirects(resposta, reverse("catalog:catalogo"),
                             fetch_redirect_response=False)

    def test_carrinho_e_pagamento_nao_ficam_na_memoria_do_navegador(self):
        for url in (reverse("cart:detalhe"),
                    reverse("payments:checkout", args=[self.pedido.numero])):
            resposta = self.client.get(url)
            self.assertIn("no-store", resposta.headers.get("Cache-Control", ""), url)


class CieloTests(BaseCheckout):
    """Driver da Cielo: o que a loja manda e o que ela entende de volta.

    A API da Cielo não é chamada de verdade — as respostas são as que a
    documentação descreve. O que se verifica aqui é a tradução: valores em
    centavos, cabeçalhos, host certo para cada operação e o status numérico
    virando o status do pedido.
    """

    def setUp(self):
        super().setUp()
        from apps.payments.gateways.cielo import CieloGateway

        self.provedor.driver = ProvedorPagamento.Driver.CIELO
        self.provedor.cielo_merchant_id = "merchant-de-teste"
        self.provedor.cielo_merchant_key = "chave-de-teste"
        self.provedor.save()
        self.gateway = CieloGateway(self.provedor)
        self.pagamento = Pagamento.objects.create(
            pedido=self.pedido, provedor=self.provedor,
            metodo=Pagamento.Metodo.CARTAO, valor=Decimal("100.00"),
        )

    def _resposta(self, corpo, status=201):
        """Finge uma resposta da Cielo, sem sair para a internet."""
        from unittest.mock import patch

        class Falsa:
            status_code = status

            def json(self):
                return corpo

        return patch("apps.payments.gateways.cielo.requests.request", return_value=Falsa())

    def test_driver_cielo_e_escolhido_quando_ha_credencial(self):
        self.assertEqual(get_gateway(self.provedor).codigo, "cielo")

    def test_sem_credencial_cai_no_simulado(self):
        """Trocar o driver sem preencher a chave não pode quebrar o checkout."""
        self.provedor.cielo_merchant_key = ""
        self.provedor.save()
        self.assertEqual(get_gateway(self.provedor).codigo, "simulado")

    def test_credenciais_vao_no_cabecalho(self):
        cabecalhos = self.gateway._headers()
        self.assertEqual(cabecalhos["MerchantId"], "merchant-de-teste")
        self.assertEqual(cabecalhos["MerchantKey"], "chave-de-teste")
        self.assertEqual(cabecalhos["Content-Type"], "application/json")

    def test_consulta_usa_o_host_de_consulta(self):
        """A Cielo recusa consulta no host transacional."""
        self.pagamento.referencia_externa = "pagamento-123"
        self.pagamento.save()
        with self._resposta({"Payment": {"Status": 2, "PaymentId": "pagamento-123"}}, 200) as chamada:
            self.gateway.consultar(self.pagamento)
        url = chamada.call_args[0][1]
        self.assertIn("apiquerysandbox", url)

    def test_autorizacao_manda_centavos_e_vai_ao_host_de_transacao(self):
        from apps.payments.gateways.base import DadosCartao

        corpo = {"Payment": {"Status": 1, "PaymentId": "p-1", "Tid": "t-1",
                             "CreditCard": {"Brand": "Visa", "CardNumber": "411111******1234"}}}
        with self._resposta(corpo) as chamada:
            resultado = self.gateway.autorizar_cartao(
                self.pagamento, DadosCartao(**CARTAO_APROVADO), parcelas=3
            )

        enviado = json.loads(chamada.call_args[1]["data"])
        self.assertEqual(enviado["Payment"]["Amount"], 10000)      # R$ 100,00
        self.assertEqual(enviado["Payment"]["Installments"], 3)
        self.assertIn("apisandbox", chamada.call_args[0][1])
        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.status, "autorizado")
        self.assertEqual(resultado.referencia_externa, "p-1")

    def test_status_da_cielo_vira_status_do_pedido(self):
        from apps.payments.gateways.cielo import MAPA_STATUS

        self.assertEqual(MAPA_STATUS[2], "pago")
        self.assertEqual(MAPA_STATUS[3], "recusado")
        self.assertEqual(MAPA_STATUS[10], "cancelado")
        self.assertEqual(MAPA_STATUS[11], "estornado")

    def test_recusa_vem_com_a_mensagem_da_cielo(self):
        from apps.payments.gateways.base import DadosCartao

        corpo = {"Payment": {"Status": 3, "PaymentId": "p-2",
                             "ReturnMessage": "Not Authorized", "ReturnCode": "05"}}
        with self._resposta(corpo):
            resultado = self.gateway.autorizar_cartao(
                self.pagamento, DadosCartao(**CARTAO_RECUSADO)
            )
        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.status, "recusado")
        self.assertEqual(resultado.codigo_retorno, "05")

    def test_erro_em_lista_vira_mensagem_legivel(self):
        """A Cielo devolve erro como lista de objetos, não como texto."""
        corpo = [{"Code": 126, "Message": "Credit Card Expiration Date is invalid"}]
        with self._resposta(corpo, status=400):
            from apps.payments.gateways.base import DadosCartao

            resultado = self.gateway.autorizar_cartao(
                self.pagamento, DadosCartao(**CARTAO_APROVADO)
            )
        self.assertFalse(resultado.sucesso)
        self.assertIn("Expiration Date", resultado.mensagem)

    def test_pix_traz_o_qrcode(self):
        corpo = {"Payment": {"Status": 12, "PaymentId": "pix-1",
                             "QrCodeString": "00020126...", "QrCodeBase64Image": "iVBOR"}}
        with self._resposta(corpo):
            resultado = self.gateway.criar_pix(self.pagamento)
        self.assertEqual(resultado.pix_qrcode, "00020126...")
        self.assertEqual(resultado.status, "processando")

    def test_webhook_consulta_o_estado_real(self):
        """O aviso diz que mudou; o status verdadeiro vem da consulta."""
        with self._resposta({"Payment": {"Status": 2, "Amount": 10000}}, 200):
            dados = self.gateway.interpretar_webhook(
                {"PaymentId": "p-9", "ChangeType": "1"}
            )
        self.assertEqual(dados["referencia_externa"], "p-9")
        self.assertEqual(dados["status"], "pago")
        self.assertEqual(dados["valor"], Decimal("100"))

    def test_webhook_sem_payment_id_e_recusado(self):
        resposta = self.client.post(
            reverse("payments:webhook_cielo"),
            data=json.dumps({"ChangeType": "1"}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_cielo_fora_do_ar_nao_derruba_o_webhook(self):
        from unittest.mock import patch

        from apps.payments.gateways.base import ErroGateway

        with patch.object(self.gateway, "_chamar", side_effect=ErroGateway("sem rede")):
            dados = self.gateway.interpretar_webhook({"PaymentId": "p-9", "ChangeType": "1"})
        self.assertEqual(dados["referencia_externa"], "p-9")
        self.assertEqual(dados["status"], "")      # fica para reprocessar
