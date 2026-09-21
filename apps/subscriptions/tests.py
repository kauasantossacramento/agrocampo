"""Assinatura de ponta a ponta: nasce do pedido, cobra no cartão na data
certa, ou lembra o cliente de pagar quando não há cartão; avisa 2 dias antes.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.cart.models import Carrinho
from apps.catalog.models import Categoria, Produto
from apps.notifications.models import Notificacao
from apps.orders.models import Pedido
from apps.orders.services import criar_pedido_do_carrinho, separar_pedido
from apps.payments.models import CartaoTokenizado, ProvedorPagamento

from .models import Assinatura, CicloAssinatura
from .services import lembrar_proximas, processar_vencidas


class AssinaturaFluxoTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(
            email="ana@exemplo.com", password="senha-forte-123", first_name="Ana",
            telefone="(75) 99999-0000",
        )
        self.cliente.enderecos.create(
            apelido="Casa", destinatario="Ana", cep="45400-000", logradouro="Rua A",
            numero="1", bairro="Centro", cidade="Valença", uf="BA", padrao=True,
        )
        categoria = Categoria.objects.create(nome="Ração")
        self.produto = Produto.objects.create(
            sku="R-1", nome="Ração Golden 15kg", categoria=categoria,
            preco=Decimal("300.00"), estoque=20, permite_assinatura=True,
        )
        self.provedor = ProvedorPagamento.ativo_padrao()

    def _assinatura(self):
        carrinho = Carrinho.objects.create(usuario=self.cliente)
        carrinho.adicionar(self.produto, 1, True, 30)
        pedido = criar_pedido_do_carrinho(carrinho, self.cliente)
        pedido.mudar_status(Pedido.Status.PAGO)
        separar_pedido(pedido)
        return Assinatura.objects.get(usuario=self.cliente)

    def _cartao(self):
        return CartaoTokenizado.objects.create(
            usuario=self.cliente, provedor=self.provedor, token="card_abc",
            bandeira="visa", ultimos_digitos="4242", validade_mes=12, validade_ano=2030,
            padrao=True,
        )

    # ---------------------------------------------------------- nascimento
    def test_pedido_recorrente_vira_assinatura_com_data_marcada(self):
        assinatura = self._assinatura()
        self.assertEqual(assinatura.status, Assinatura.Status.ATIVA)
        self.assertEqual(assinatura.frequencia_dias, 30)
        self.assertEqual(assinatura.proxima_entrega, timezone.localdate() + timedelta(days=30))
        # sem desconto por padrão: o preço da assinatura é o preço cheio
        self.assertEqual(assinatura.preco_unitario, Decimal("300.00"))

    def test_antes_da_data_nada_e_cobrado(self):
        self._assinatura()
        self.assertEqual(processar_vencidas(), [])
        self.assertEqual(CicloAssinatura.objects.count(), 0)

    # ------------------------------------------------- cobrança automática
    def test_na_data_cobra_o_cartao_e_gera_o_pedido(self):
        assinatura = self._assinatura()
        assinatura.cartao = self._cartao()
        assinatura.proxima_entrega = timezone.localdate()
        assinatura.save()

        ciclos = processar_vencidas()

        self.assertEqual(len(ciclos), 1)
        ciclo = ciclos[0]
        self.assertEqual(ciclo.status, CicloAssinatura.Status.PAGO)
        self.assertIsNotNone(ciclo.pedido)
        # o pedido do ciclo já entrou em separação (pago -> separação, sem aprovação)
        self.assertEqual(ciclo.pedido.status, Pedido.Status.EM_SEPARACAO)
        self.assertTrue(ciclo.pedido.pagamentos.filter(status="pago").exists())
        assinatura.refresh_from_db()
        self.assertEqual(assinatura.proxima_entrega, timezone.localdate() + timedelta(days=30))
        self.assertEqual(assinatura.falhas_consecutivas, 0)
        self.assertTrue(
            Notificacao.objects.filter(destinatario=self.cliente, titulo="Assinatura renovada").exists()
        )

    def test_cobranca_recusada_reagenda_em_3_dias_e_cancela_na_terceira(self):
        from apps.payments.gateways.base import ResultadoPagamento

        assinatura = self._assinatura()
        assinatura.cartao = self._cartao()
        assinatura.proxima_entrega = timezone.localdate()
        assinatura.save()

        recusa = ResultadoPagamento(sucesso=False, status="recusado", mensagem="Cartão recusado")
        with mock.patch("apps.payments.gateways.simulado.SimuladoGateway.cobrar_com_token", return_value=recusa):
            for tentativa in range(3):
                assinatura.proxima_entrega = timezone.localdate()
                assinatura.save()
                processar_vencidas()
                assinatura.refresh_from_db()
                if tentativa < 2:
                    self.assertEqual(assinatura.status, Assinatura.Status.INADIMPLENTE)
                    self.assertEqual(assinatura.proxima_entrega, timezone.localdate() + timedelta(days=3))
        self.assertEqual(assinatura.status, Assinatura.Status.CANCELADA)
        self.assertEqual(assinatura.falhas_consecutivas, 3)

    # ------------------------------------------------------ modo lembrete
    def test_sem_cartao_gera_pedido_para_pagar_e_lembra_sem_contar_falha(self):
        assinatura = self._assinatura()
        self.assertIsNone(assinatura.cartao)
        assinatura.proxima_entrega = timezone.localdate()
        assinatura.save()

        ciclos = processar_vencidas()

        ciclo = ciclos[0]
        self.assertEqual(ciclo.status, CicloAssinatura.Status.AGENDADO)
        self.assertEqual(ciclo.pedido.status, Pedido.Status.AGUARDANDO_PAGAMENTO)
        self.assertEqual(ciclo.pedido.total, Decimal("300.00"))
        assinatura.refresh_from_db()
        self.assertEqual(assinatura.status, Assinatura.Status.ATIVA)
        self.assertEqual(assinatura.falhas_consecutivas, 0)
        self.assertEqual(assinatura.proxima_entrega, timezone.localdate() + timedelta(days=30))
        aviso = Notificacao.objects.get(destinatario=self.cliente, titulo="Hora de renovar sua assinatura")
        self.assertIn(ciclo.pedido.numero, aviso.mensagem)
        self.assertEqual(aviso.link, ciclo.pedido.get_absolute_url())

    # ---------------------------------------------------------- aviso prévio
    def test_aviso_dois_dias_antes_uma_vez_so(self):
        assinatura = self._assinatura()
        assinatura.proxima_entrega = timezone.localdate() + timedelta(days=2)
        assinatura.save()

        self.assertEqual(len(lembrar_proximas()), 1)
        self.assertEqual(len(lembrar_proximas()), 0)  # não repete no mesmo dia
        aviso = Notificacao.objects.get(titulo="Sua assinatura renova em 2 dias")
        self.assertIn("você recebe o pedido para pagar", aviso.mensagem)

        assinatura.cartao = self._cartao()
        assinatura.save()
        Notificacao.objects.all().delete()
        lembrar_proximas()
        aviso = Notificacao.objects.get(titulo="Sua assinatura renova em 2 dias")
        self.assertIn("cartão final 4242", aviso.mensagem)

    def test_comando_do_cron_roda_tudo(self):
        assinatura = self._assinatura()
        assinatura.proxima_entrega = timezone.localdate()
        assinatura.save()
        from io import StringIO

        saida = StringIO()
        call_command("processar_assinaturas", stdout=saida)
        self.assertIn("1 lembrete(s) para pagar", saida.getvalue())
        self.assertEqual(CicloAssinatura.objects.count(), 1)
