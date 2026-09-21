"""Silvinha: contexto honesto, fallback sem chave e widget só onde deve."""
import json
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings

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
        self.assertIn("gemini-2.5-flash", post.call_args.args[0])
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
