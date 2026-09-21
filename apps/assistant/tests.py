"""Silvinha: contexto honesto, fallback sem chave e widget só onde deve."""
import json
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.catalog.models import Categoria, Produto
from apps.core.models import SiteConfig
from apps.shipping.models import Cidade

from . import gemini, services
from .models import ConversaAssistente


def _gemini_ok(texto):
    r = mock.Mock()
    r.status_code = 200
    r.json.return_value = {"candidates": [{"content": {"parts": [{"text": texto}]}}]}
    return r


@override_settings(SITE_URL="https://loja.teste")
class SilvinhaTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nome="Ração")
        self.racao = Produto.objects.create(
            sku="R-1", nome="Ração Golden Cães Adultos 15kg", categoria=categoria,
            preco=Decimal("289.90"), estoque=3, resumo="Para cães adultos de porte médio.",
        )
        Produto.objects.create(
            sku="S-1", nome="Sal Mineral Bovino 25kg", categoria=categoria,
            preco=Decimal("120.00"), estoque=0,
        )
        Cidade.objects.create(nome="Valença", uf="BA", sede=True, frete=Decimal("8"))
        Cidade.objects.create(nome="Cairu", uf="BA", frete=Decimal("25"), dias_entrega="4")
        config = SiteConfig.load()
        config.assistente_ativo = True
        config.gemini_api_key = "chave-teste"
        config.whatsapp = "(75) 3641-0000"
        config.save()

    # ------------------------------------------------------------ contexto
    def test_contexto_traz_catalogo_relevante_e_entrega(self):
        instrucoes = services.montar_instrucoes("tem ração para cachorro adulto?")
        self.assertIn("Ração Golden Cães Adultos 15kg", instrucoes)
        self.assertIn("R$ 289,90", instrucoes)
        self.assertIn("https://loja.teste/produto/", instrucoes)
        self.assertIn("Valença/BA", instrucoes)
        self.assertIn("Cairu/BA", instrucoes)
        self.assertIn("somente às sextas", instrucoes)
        self.assertIn("(75) 3641-0000", instrucoes)
        self.assertIn("Nunca invente", instrucoes)

    def test_produto_sem_estoque_e_marcado(self):
        instrucoes = services.montar_instrucoes("sal mineral")
        self.assertIn("Sal Mineral Bovino 25kg", instrucoes)
        self.assertIn("SEM estoque", instrucoes)

    def test_pagina_de_produto_entra_no_contexto(self):
        instrucoes = services.montar_instrucoes("serve para filhote?", self.racao)
        self.assertIn("O CLIENTE ESTÁ NA PÁGINA DO PRODUTO: Ração Golden", instrucoes)

    # ------------------------------------------------------------- endpoint
    @mock.patch("apps.assistant.gemini.requests.post", return_value=_gemini_ok("Temos sim! Ração Golden."))
    def test_conversar_responde_e_registra(self, post):
        r = self.client.post(
            "/assistente/conversar/",
            data=json.dumps({"pergunta": "tem ração de cachorro?", "historico": [], "produto": self.racao.slug}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["texto"], "Temos sim! Ração Golden.")
        self.assertTrue(r.json()["ok"])
        corpo = post.call_args.kwargs["json"]
        self.assertEqual(post.call_args.kwargs["params"]["key"], "chave-teste")
        self.assertIn("gemini-3.6-flash", post.call_args.args[0])
        self.assertEqual(corpo["contents"][-1]["role"], "user")
        conversa = ConversaAssistente.objects.get()
        self.assertEqual(conversa.produto, self.racao)
        self.assertFalse(conversa.falhou)

    @mock.patch("apps.assistant.gemini.requests.post")
    def test_sem_chave_responde_com_whatsapp(self, post):
        config = SiteConfig.load()
        config.gemini_api_key = ""
        config.save()
        r = self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "oi"}),
                             content_type="application/json")
        post.assert_not_called()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertIn("(75) 3641-0000", r.json()["texto"])
        self.assertTrue(ConversaAssistente.objects.get().falhou)

    @mock.patch("apps.assistant.gemini.requests.post", side_effect=gemini.requests.ConnectionError("x"))
    def test_gemini_fora_nao_quebra(self, post):
        r = self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "oi"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertIn("dificuldade", r.json()["texto"])

    def test_desligada_da_404(self):
        config = SiteConfig.load()
        config.assistente_ativo = False
        config.save()
        r = self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "oi"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 404)

    @mock.patch("apps.assistant.gemini.requests.post", return_value=_gemini_ok("ok"))
    def test_limite_por_hora(self, post):
        for _ in range(services.LIMITE_POR_HORA):
            self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "oi"}),
                             content_type="application/json")
        r = self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "oi"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 429)

    # --------------------------------------------------------------- widget
    def test_widget_aparece_na_home_e_no_produto_mas_nao_no_catalogo(self):
        self.assertContains(self.client.get("/"), 'id="silvinha"')
        self.assertContains(self.client.get(self.racao.get_absolute_url()), 'data-produto="%s"' % self.racao.slug)
        self.assertNotContains(self.client.get("/catalogo/"), 'id="silvinha"')

    def test_widget_some_quando_desligada(self):
        config = SiteConfig.load()
        config.assistente_ativo = False
        config.save()
        self.assertNotContains(self.client.get("/"), 'id="silvinha"')


class CompraPeloChatTests(TestCase):
    """A IA propõe [[COMPRAR ...]], o cliente confirma; login/cadastro no chat."""

    def setUp(self):
        categoria = Categoria.objects.create(nome="Ração")
        self.racao = Produto.objects.create(
            sku="R-1", nome="Ração Golden 15kg", categoria=categoria,
            preco=Decimal("289.90"), estoque=3, publicado=True,
        )
        config = SiteConfig.load()
        config.assistente_ativo = True
        config.gemini_api_key = "chave-teste"
        config.save()

    def _post(self, dados):
        return self.client.post("/assistente/acao/", data=json.dumps(dados), content_type="application/json")

    @mock.patch("apps.assistant.gemini.requests.post",
                return_value=_gemini_ok("Boa escolha! O botão de compra vai aparecer.\n[[COMPRAR codigo=racao-golden-15kg qtd=2]]"))
    def test_ia_propoe_a_compra_e_a_marca_some_do_texto(self, post):
        r = self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "quero 2 rações golden"}),
                             content_type="application/json")
        d = r.json()
        self.assertNotIn("[[COMPRAR", d["texto"])
        self.assertEqual(d["acao"]["tipo"], "comprar")
        self.assertEqual(d["acao"]["produto"]["slug"], "racao-golden-15kg")
        self.assertEqual(d["acao"]["quantidade"], 2)
        self.assertIn("codigo: racao-golden-15kg", services.montar_instrucoes("ração"))

    @mock.patch("apps.assistant.gemini.requests.post",
                return_value=_gemini_ok("Ok\n[[COMPRAR codigo=nao-existe qtd=1]]"))
    def test_codigo_invalido_nao_vira_acao(self, post):
        d = self.client.post("/assistente/conversar/", data=json.dumps({"pergunta": "x"}),
                             content_type="application/json").json()
        self.assertNotIn("acao", d)

    def test_comprar_sem_login_pede_acesso(self):
        d = self._post({"tipo": "comprar", "produto": self.racao.slug, "quantidade": 1}).json()
        self.assertTrue(d["precisa_login"])

    def test_cadastro_no_chat_loga_e_compra(self):
        d = self._post({"tipo": "cadastrar", "nome": "Ana Souza", "email": "ana@exemplo.com",
                        "telefone": "(75) 99999-0000", "senha": "senha-forte-123"}).json()
        self.assertTrue(d["ok"]); self.assertTrue(d["criado"]); self.assertEqual(d["nome"], "Ana")
        u = User.objects.get(email="ana@exemplo.com")
        self.assertEqual(u.first_name, "Ana"); self.assertEqual(u.last_name, "Souza")
        self.assertTrue(u.aceita_contato_whatsapp)
        d = self._post({"tipo": "comprar", "produto": self.racao.slug, "quantidade": 2}).json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["checkout"], "/carrinho/checkout/")
        self.assertEqual(d["quantidade_carrinho"], 2)

    def test_cadastro_invalido_devolve_erros(self):
        d = self._post({"tipo": "cadastrar", "nome": "", "email": "x", "telefone": "1", "senha": "123"}).json()
        self.assertFalse(d["ok"]); self.assertIn("email", d["erros"])

    def test_login_no_chat(self):
        User.objects.create_user(email="joao@exemplo.com", password="senha-forte-123", first_name="João")
        d = self._post({"tipo": "entrar", "email": "joao@exemplo.com", "senha": "errada"}).json()
        self.assertFalse(d["ok"])
        d = self._post({"tipo": "entrar", "email": "JOAO@exemplo.com", "senha": "senha-forte-123"}).json()
        self.assertTrue(d["ok"]); self.assertEqual(d["nome"], "João")
        d = self._post({"tipo": "comprar", "produto": self.racao.slug, "quantidade": 5}).json()
        self.assertFalse(d["ok"]); self.assertIn("estoque", d["erro"])


class CartoesDeProdutoTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nome="Ração")
        self.racao = Produto.objects.create(sku="R-1", nome="Ração Golden 15kg", categoria=categoria,
                                            preco=Decimal("289.90"), estoque=3, publicado=True)
        self.comedouro = Produto.objects.create(sku="C-1", nome="Comedouro Inox", categoria=categoria,
                                                preco=Decimal("79.90"), estoque=0, publicado=True)

    def test_links_de_produto_viram_cartoes_e_saem_do_texto(self):
        texto = ("Temos a Ração Golden por R$ 289,90 e o Comedouro Inox.\n\n"
                 "Você pode conferir mais detalhes nestes links:\n"
                 "- Ração Golden: https://agrocampo.online/produto/racao-golden-15kg/\n"
                 "- Comedouro: https://agrocampo.online/produto/comedouro-inox/\n\n"
                 "Se quiser, me avise a quantidade!")
        limpo, cartoes = services.produtos_citados(texto)
        self.assertEqual([c["slug"] for c in cartoes], ["racao-golden-15kg", "comedouro-inox"])
        self.assertEqual(cartoes[0]["preco"], "R$ 289,90")
        self.assertTrue(cartoes[0]["em_estoque"]); self.assertFalse(cartoes[1]["em_estoque"])
        self.assertNotIn("http", limpo)
        self.assertNotIn("nestes links", limpo)
        self.assertNotIn("- Ração Golden:", limpo)
        self.assertIn("Se quiser, me avise a quantidade!", limpo)

    def test_sem_links_nada_muda(self):
        limpo, cartoes = services.produtos_citados("Oi! Como posso ajudar?")
        self.assertEqual(cartoes, []); self.assertEqual(limpo, "Oi! Como posso ajudar?")

    def test_markdown_de_link_vira_cartao_e_nome_limpo(self):
        texto = "Temos a [Ração Golden 15kg](racao-golden-15kg) por R$ 289,90 e o [Comedouro Inox](https://x/produto/comedouro-inox/)."
        limpo, cartoes = services.produtos_citados(texto)
        self.assertEqual([c["slug"] for c in cartoes], ["racao-golden-15kg", "comedouro-inox"])
        self.assertEqual(limpo, "Temos a Ração Golden 15kg por R$ 289,90 e o Comedouro Inox.")

    def test_url_com_dominio_errado_ainda_vira_cartao(self):
        limpo, cartoes = services.produtos_citados("Veja: http://loja.com/racao-golden-15kg e fim.")
        self.assertEqual(cartoes[0]["slug"], "racao-golden-15kg")
        self.assertEqual(cartoes[0]["url"], "/produto/racao-golden-15kg/")
        self.assertNotIn("http", limpo)
