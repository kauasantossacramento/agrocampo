"""Regras de entrega: cidade, ilha e dia da semana."""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Endereco, User
from apps.core.models import SiteConfig
from apps.shipping.models import Cidade, Localidade, calcular_frete


class BaseEntrega(TestCase):
    @classmethod
    def setUpTestData(cls):
        config = SiteConfig.load()
        config.frete_valor = Decimal("24.90")
        config.frete_gratis_acima_de = Decimal("199.00")
        config.entrega_a_partir_de = time(15, 0)
        config.save()

        cls.valenca = Cidade.objects.create(
            nome="Valença", uf="BA", sede=True,
            frete=Decimal("8.00"), prazo_dias=0,
        )
        cls.taperoa = Cidade.objects.create(
            nome="Taperoá", uf="BA",
            frete=Decimal("18.00"), dias_entrega="4", prazo_dias=1,
        )
        cls.guaibim = Localidade.objects.create(
            cidade=cls.valenca, nome="Ilha do Guaibim",
            frete_adicional=Decimal("10.00"), acesso_por_barco=True,
        )

        cls.cliente = User.objects.create_user(
            email="cliente@teste.com", username="cliente", password="x"
        )

    def _endereco(self, cidade=None, localidade=None):
        return Endereco.objects.create(
            usuario=self.cliente, destinatario="Cliente", cep="45400-000",
            logradouro="Rua A", numero="1", bairro="Centro",
            cidade=(cidade.nome if cidade else "Outra"), uf="BA",
            cidade_atendida=cidade, localidade=localidade,
        )


class FreteTests(BaseEntrega):
    def test_frete_da_cidade_sede(self):
        resultado = calcular_frete(self._endereco(self.valenca), Decimal("50"))
        self.assertEqual(resultado["valor"], Decimal("8.00"))
        self.assertTrue(resultado["atendida"])

    def test_frete_gratis_acima_do_limite_global(self):
        resultado = calcular_frete(self._endereco(self.valenca), Decimal("250"))
        self.assertEqual(resultado["valor"], Decimal("0"))

    def test_ilha_soma_o_acrescimo_mesmo_com_frete_gratis(self):
        """A travessia é custo real: frete grátis no pedido não paga o barco."""
        endereco = self._endereco(self.valenca, self.guaibim)
        resultado = calcular_frete(endereco, Decimal("250"))
        self.assertEqual(resultado["valor"], Decimal("10.00"))
        self.assertTrue(any("travessia" in a for a in resultado["avisos"]))

    def test_cidade_com_limite_proprio_ignora_o_global(self):
        self.taperoa.frete_gratis_acima_de = Decimal("0")
        self.taperoa.save()
        resultado = calcular_frete(self._endereco(self.taperoa), Decimal("500"))
        self.assertEqual(resultado["valor"], Decimal("18.00"))

    def test_cidade_nao_atendida_cai_no_valor_global_e_avisa(self):
        resultado = calcular_frete(self._endereco(None), Decimal("50"))
        self.assertEqual(resultado["valor"], Decimal("24.90"))
        self.assertFalse(resultado["atendida"])
        self.assertTrue(resultado["avisos"])

    def test_horario_da_loja_entra_nos_avisos(self):
        resultado = calcular_frete(self._endereco(self.valenca), Decimal("50"))
        self.assertTrue(any("15:00" in a for a in resultado["avisos"]))


class DiasDeEntregaTests(BaseEntrega):
    def test_cidade_sem_dias_entrega_de_segunda_a_sexta(self):
        self.assertEqual(self.valenca.dias, [0, 1, 2, 3, 4])
        self.assertEqual(self.valenca.dias_legivel, "de segunda a sexta")

    def test_fora_de_valenca_somente_na_sexta(self):
        self.assertEqual(self.taperoa.dias, [4])
        self.assertEqual(self.taperoa.dias_legivel, "somente às sextas")

        # segunda-feira: a próxima entrega cai na sexta da mesma semana
        segunda = date(2026, 8, 24)
        self.assertEqual(self.taperoa.proxima_entrega(segunda).weekday(), 4)

    def test_prazo_extra_da_localidade_empurra_a_data(self):
        self.guaibim.prazo_extra_dias = 2
        self.guaibim.save()
        endereco = self._endereco(self.valenca, self.guaibim)
        sem_ilha = calcular_frete(self._endereco(self.valenca), Decimal("50"))["prazo"]
        com_ilha = calcular_frete(endereco, Decimal("50"))["prazo"]
        self.assertEqual((com_ilha - sem_ilha).days, 2)

    def test_dias_invalidos_nao_quebram_a_leitura(self):
        self.taperoa.dias_entrega = "9, x, 4"
        self.assertEqual(self.taperoa.dias, [4])

    def test_so_uma_cidade_fica_como_sede(self):
        self.taperoa.sede = True
        self.taperoa.save()
        self.valenca.refresh_from_db()
        self.assertFalse(self.valenca.sede)


class PaginaOndeEntregamosTests(BaseEntrega):
    def test_lista_as_cidades_atendidas(self):
        from django.urls import reverse

        resposta = self.client.get(reverse("shipping:onde_entregamos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Valença")
        self.assertContains(resposta, "Taperoá")
        self.assertContains(resposta, "Ilha do Guaibim")
        self.assertContains(resposta, "omente às sextas")   # capfirst no template

    def test_cidade_desativada_some_da_lista(self):
        from django.urls import reverse

        self.taperoa.ativo = False
        self.taperoa.save()
        resposta = self.client.get(reverse("shipping:onde_entregamos"))
        self.assertNotContains(resposta, "Taperoá")

    def test_sem_cidades_a_pagina_ainda_responde(self):
        from django.urls import reverse

        from apps.shipping.models import Cidade

        Cidade.objects.all().delete()
        resposta = self.client.get(reverse("shipping:onde_entregamos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Fale com a loja")


class EntregaNoCarrinhoTests(BaseEntrega):
    """O cliente precisa ver o frete e o prazo antes de finalizar."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Produto

        self.cliente.set_password("senha-forte-123")
        self.cliente.save()
        categoria = Categoria.objects.create(nome="Ração")
        self.produto = Produto.objects.create(
            sku="E-1", nome="Ração teste", categoria=categoria,
            preco=Decimal("50.00"), estoque=10, publicado=True,
        )
        self.client.force_login(self.cliente)

    def _com_endereco(self, cidade, localidade=None):
        self.cliente.enderecos.all().delete()
        self._endereco(cidade, localidade).__class__.objects.filter(
            usuario=self.cliente
        ).update(padrao=True)
        self.client.post(f"/carrinho/adicionar/{self.produto.slug}/", {"quantidade": 1})

    def test_carrinho_mostra_frete_e_prazo_da_cidade(self):
        self._com_endereco(self.valenca)
        html = self.client.get("/carrinho/").content.decode()

        self.assertIn("Valença", html)
        self.assertIn("Chega em", html)
        self.assertIn("8,00", html)   # frete da sede

    def test_carrinho_soma_o_acrescimo_da_ilha(self):
        self._com_endereco(self.valenca, self.guaibim)
        html = self.client.get("/carrinho/").content.decode()

        self.assertIn("18,00", html)   # 8,00 da cidade + 10,00 da travessia

    def test_checkout_avisa_quando_a_cidade_nao_e_atendida(self):
        self._com_endereco(None)
        html = self.client.get("/carrinho/checkout/").content.decode()

        self.assertIn("Confirmamos a entrega por WhatsApp", html)


class SemFretePrometidoSemQuererTests(TestCase):
    """Cidade com frete 0,00 anuncia entrega grátis — não pode vir ligada."""

    def test_a_cidade_semeada_nasce_desativada(self):
        from django.core.management import call_command

        from apps.shipping.models import Cidade

        call_command("seed", verbosity=0)
        valenca = Cidade.objects.get(nome="Valença")
        self.assertFalse(valenca.ativo)
        self.assertNotIn(valenca, Cidade.objects.atendidas())
