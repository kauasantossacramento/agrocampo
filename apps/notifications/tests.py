"""WhatsApp automático: interruptor, consentimento e resiliência."""
from unittest import mock

import requests
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.core.models import SiteConfig

from . import whatsapp
from .models import MensagemWhatsApp, Notificacao
from .services import notificar


def _resposta(status=200, corpo=None):
    r = mock.Mock()
    r.ok = 200 <= status < 300
    r.status_code = status
    r.json.return_value = corpo or {"ok": True}
    r.text = str(corpo or "")
    return r


@override_settings(WHATSAPP_WEB_URL="http://whatsapp:3000", WHATSAPP_WEB_TOKEN="segredo",
                   SITE_URL="https://loja.teste")
class WhatsAppTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(
            email="ana@exemplo.com", password="senha-forte-123", first_name="Ana",
            telefone="(75) 99999-0000", aceita_contato_whatsapp=True,
        )
        config = SiteConfig.load()
        config.whatsapp_auto_ativo = True
        config.save()

    def test_normaliza_numero_brasileiro(self):
        self.assertEqual(whatsapp.normalizar_numero("(75) 99999-0000"), "5575999990000")
        self.assertEqual(whatsapp.normalizar_numero("5575999990000"), "5575999990000")
        self.assertEqual(whatsapp.normalizar_numero("123"), "")

    @mock.patch("apps.notifications.whatsapp.requests.post", return_value=_resposta())
    def test_notificar_envia_e_marca(self, post):
        n = notificar(destinatario=self.cliente, titulo="Pedido confirmado!",
                      mensagem="Está em separação.", link="/pedidos/PED-1/", whatsapp=True)
        post.assert_called_once()
        corpo = post.call_args.kwargs["json"]
        self.assertEqual(corpo["numero"], "5575999990000")
        self.assertIn("Olá, Ana!", corpo["texto"])
        self.assertIn("https://loja.teste/pedidos/PED-1/", corpo["texto"])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer segredo")
        n.refresh_from_db()
        self.assertTrue(n.enviada_por_whatsapp)
        self.assertEqual(MensagemWhatsApp.objects.get().status, MensagemWhatsApp.Status.ENVIADA)

    @mock.patch("apps.notifications.whatsapp.requests.post")
    def test_interruptor_desligado_nao_envia(self, post):
        config = SiteConfig.load()
        config.whatsapp_auto_ativo = False
        config.save()
        notificar(destinatario=self.cliente, titulo="x", whatsapp=True)
        post.assert_not_called()
        self.assertFalse(MensagemWhatsApp.objects.exists())

    @mock.patch("apps.notifications.whatsapp.requests.post")
    def test_sem_consentimento_nao_envia(self, post):
        self.cliente.aceita_contato_whatsapp = False
        self.cliente.save()
        notificar(destinatario=self.cliente, titulo="x", whatsapp=True)
        post.assert_not_called()

    @mock.patch("apps.notifications.whatsapp.requests.post",
                side_effect=requests.ConnectionError("recusado"))
    def test_servico_fora_nao_derruba_o_fluxo(self, post):
        n = notificar(destinatario=self.cliente, titulo="x", whatsapp=True)
        self.assertIsNotNone(n.pk)
        registro = MensagemWhatsApp.objects.get()
        self.assertEqual(registro.status, MensagemWhatsApp.Status.FALHOU)
        self.assertIn("recusado", registro.erro)

    @mock.patch("apps.notifications.whatsapp.requests.post",
                return_value=_resposta(503, {"erro": "sessão aguardando_qr"}))
    def test_erro_do_servico_fica_registrado(self, post):
        registro = whatsapp.enviar("75999990000", "oi", ignorar_interruptor=True)
        self.assertEqual(registro.status, MensagemWhatsApp.Status.FALHOU)
        self.assertIn("aguardando_qr", registro.erro)

    @override_settings(WHATSAPP_WEB_URL="", WHATSAPP_WEB_TOKEN="")
    @mock.patch("apps.notifications.whatsapp.requests.post")
    def test_sem_configuracao_ignora(self, post):
        registro = whatsapp.enviar("75999990000", "oi", ignorar_interruptor=True)
        post.assert_not_called()
        self.assertEqual(registro.status, MensagemWhatsApp.Status.IGNORADA)
        self.assertEqual(whatsapp.status_sessao()["estado"], "nao_configurado")

    @mock.patch("apps.notifications.whatsapp.requests.get",
                return_value=_resposta(200, {"estado": "aguardando_qr", "qr": "data:image/png;base64,x"}))
    def test_painel_consulta_status(self, get):
        lojista = User.objects.create_user(
            email="loja@exemplo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )
        self.client.force_login(lojista)
        r = self.client.get("/painel/whatsapp/status/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["estado"], "aguardando_qr")
        self.assertTrue(r.json()["qr"].startswith("data:image"))

    def test_status_exige_operador(self):
        self.client.force_login(self.cliente)
        r = self.client.get("/painel/whatsapp/status/")
        self.assertNotEqual(r.status_code, 200)
