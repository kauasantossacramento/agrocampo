"""Cadastro e contato do cliente."""
from django.test import TestCase

from apps.accounts.forms import CadastroForm


class WhatsAppNoCadastroTests(TestCase):
    """A loja precisa de um número para avisar sobre item em falta."""

    def _dados(self, **extra):
        base = {
            "first_name": "Ana", "last_name": "Silva",
            "email": "ana@exemplo.com", "telefone": "(75) 98888-7777",
            "cpf": "", "password1": "senha-forte-123", "password2": "senha-forte-123",
        }
        base.update(extra)
        return base

    def test_cadastro_sem_whatsapp_e_recusado(self):
        form = CadastroForm(data=self._dados(telefone=""))
        self.assertFalse(form.is_valid())
        self.assertIn("telefone", form.errors)

    def test_numero_curto_demais_e_recusado(self):
        form = CadastroForm(data=self._dados(telefone="99999"))
        self.assertFalse(form.is_valid())
        self.assertIn("DDD", " ".join(form.errors["telefone"]))

    def test_cadastro_guarda_o_numero_e_o_consentimento(self):
        form = CadastroForm(data=self._dados(aceita_contato_whatsapp="on"))
        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()
        self.assertEqual(usuario.telefone, "(75) 98888-7777")
        self.assertTrue(usuario.aceita_contato_whatsapp)

    def test_link_do_whatsapp_leva_o_ddi_do_brasil(self):
        form = CadastroForm(data=self._dados(aceita_contato_whatsapp="on"))
        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()
        self.assertEqual(usuario.whatsapp_url, "https://wa.me/5575988887777")

    def test_quem_desmarca_a_caixa_nao_e_chamado(self):
        """Sem consentimento não há link — nem para a loja, nem no painel."""
        form = CadastroForm(data=self._dados())   # caixa desmarcada
        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()
        self.assertFalse(usuario.aceita_contato_whatsapp)
        self.assertEqual(usuario.whatsapp_url, "")


class EntrarOuCadastrarTests(TestCase):
    """Quem clica em "Comprar agora" sem conta escolhe antes de digitar."""

    def test_destino_de_compra_mostra_as_duas_portas(self):
        html = self.client.get("/conta/entrar/?next=/pagamento/").content.decode()
        self.assertIn("Entrar na sua conta", html)
        self.assertIn("Cadastrar-se agora!", html)
        self.assertNotIn('name="password"', html)

    def test_escolhendo_entrar_vem_o_formulario(self):
        html = self.client.get("/conta/entrar/?acao=entrar&next=/pagamento/").content.decode()
        self.assertIn('name="password"', html)

    def test_login_comum_continua_indo_direto_ao_formulario(self):
        html = self.client.get("/conta/entrar/").content.decode()
        self.assertIn('name="password"', html)
        self.assertNotIn("Cadastrar-se agora!", html)

    def test_cadastro_tem_os_tres_passos(self):
        html = self.client.get("/conta/cadastrar/").content.decode()
        for passo in ("1", "2", "3"):
            self.assertIn(f'data-cadastro-tela="{passo}"', html)
        self.assertIn("data-cadastro-avancar", html)

    def test_cadastro_continua_sendo_um_post_so(self):
        """Sem JS os três blocos vão juntos: um formulário, um envio."""
        resposta = self.client.post("/conta/cadastrar/", {
            "first_name": "Maria", "last_name": "Silva",
            "email": "maria@exemplo.com", "telefone": "(75) 98888-7777",
            "cpf": "", "aceita_contato_whatsapp": "on",
            "password1": "senha-forte-123", "password2": "senha-forte-123",
            "next": "/",
        })
        self.assertEqual(resposta.status_code, 302)
        from apps.accounts.models import User
        self.assertTrue(User.objects.filter(email="maria@exemplo.com").exists())
