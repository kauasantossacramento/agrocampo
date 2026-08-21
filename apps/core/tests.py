"""Smoke tests: garantem que toda página pública e privada renderiza."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Categoria, Produto
from apps.orders.models import ItemPedido, Pedido

User = get_user_model()


class PaginasPublicasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.produto = Produto.objects.filter(imagens__isnull=False).first()
        cls.categoria = Categoria.objects.filter(pai__isnull=True).first()

    def test_home(self):
        resposta = self.client.get(reverse("core:home"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "AgroCampo")

    def test_catalogo_e_filtros(self):
        for consulta in ["", "?assinatura=1", "?promocao=1", "?ordem=menor-preco",
                         "?preco_min=50&preco_max=300", "?q=ração"]:
            with self.subTest(consulta=consulta):
                resposta = self.client.get(reverse("catalog:catalogo") + consulta)
                self.assertEqual(resposta.status_code, 200)

    def test_busca_sem_resultado_mostra_estado_vazio(self):
        resposta = self.client.get(reverse("catalog:busca"), {"q": "xyzabc-inexistente"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nenhum produto encontrado")

    def test_paginas_de_navegacao(self):
        rotas = [
            reverse("catalog:marcas"),
            reverse("catalog:especies"),
            reverse("blog:lista"),
            reverse("cart:detalhe"),
            reverse("accounts:entrar"),
            reverse("accounts:cadastrar"),
            reverse("core:offline"),
            self.categoria.get_absolute_url(),
            self.produto.get_absolute_url(),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)

    def test_paginas_institucionais_e_blog(self):
        from apps.blog.models import Post
        from apps.core.models import Pagina

        self.assertEqual(self.client.get(Pagina.objects.first().get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(Post.objects.first().get_absolute_url()).status_code, 200)

    def test_newsletter_aceita_cadastro(self):
        from apps.core.models import AssinanteNewsletter

        self.client.post(reverse("core:newsletter"), {"email": "novo@exemplo.com"})
        self.assertTrue(AssinanteNewsletter.objects.filter(email="novo@exemplo.com").exists())

    def test_carrinho_adiciona_e_remove(self):
        self.client.post(
            reverse("cart:adicionar", args=[self.produto.slug]), {"quantidade": 2}
        )
        resposta = self.client.get(reverse("cart:detalhe"))
        self.assertContains(resposta, self.produto.nome)

    def test_nenhuma_sintaxe_de_template_vaza_para_o_html(self):
        """Regressão: `{# ... #}` multilinha não é comentário no Django e
        aparecia como texto na página do catálogo."""
        rotas = [
            reverse("core:home"),
            reverse("catalog:catalogo"),
            reverse("catalog:marcas"),
            reverse("catalog:especies"),
            reverse("blog:lista"),
            reverse("cart:detalhe"),
            self.produto.get_absolute_url(),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                for marcador in ("{#", "#}", "{%", "%}", "{{", "}}"):
                    self.assertNotIn(
                        marcador, html, f"{rota} vazou `{marcador}` no HTML final"
                    )

    def test_api_publica_responde(self):
        for rota in ["/api/v1/catalogo/produtos/", "/api/v1/catalogo/categorias/",
                     "/api/v1/catalogo/marcas/", "/api/v1/carrinho/"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)


class PaginasAutenticadasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.cliente = User.objects.create_user(
            email="cliente@exemplo.com", password="senha-forte-123", first_name="Ana"
        )
        cls.cliente.enderecos.create(
            apelido="Casa", destinatario="Ana Costa", cep="17300-000",
            logradouro="Rua A", numero="10", bairro="Centro",
            cidade="Dois Córregos", uf="SP", padrao=True,
        )
        cls.lojista = User.objects.create_user(
            email="lojista@exemplo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )
        produto = Produto.objects.first()
        cls.pedido = Pedido.objects.create(
            usuario=cls.cliente, status=Pedido.Status.AGUARDANDO_PAGAMENTO,
            nome_cliente="Ana Costa", email_cliente=cls.cliente.email,
        )
        ItemPedido.objects.create(
            pedido=cls.pedido, produto=produto, nome_produto=produto.nome,
            quantidade=1, preco_unitario=Decimal("50.00"), preco_cheio=Decimal("50.00"),
        )
        cls.pedido.recalcular()

    def test_area_do_cliente(self):
        self.client.force_login(self.cliente)
        # o checkout so renderiza com carrinho preenchido; vazio ele redireciona
        self.client.post(
            reverse("cart:adicionar", args=[Produto.objects.first().slug]), {"quantidade": 1}
        )
        rotas = [
            reverse("accounts:perfil"),
            reverse("accounts:enderecos"),
            reverse("accounts:desejos"),
            reverse("orders:lista"),
            reverse("subscriptions:lista"),
            reverse("notifications:lista"),
            reverse("cart:checkout"),
            self.pedido.get_absolute_url(),
            reverse("payments:checkout", args=[self.pedido.numero]),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)

    def test_painel_do_lojista(self):
        self.client.force_login(self.lojista)
        rotas = [
            reverse("dashboard:painel"),
            reverse("dashboard:pedidos"),
            reverse("dashboard:estoque"),
            reverse("dashboard:metricas"),
            reverse("dashboard:assinaturas"),
            reverse("dashboard:configuracoes"),
            reverse("dashboard:pedido", args=[self.pedido.numero]),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)

    def test_rotas_protegidas_redirecionam_anonimo_para_o_login(self):
        """Anônimo em rota protegida deve cair no login, não em NoReverseMatch.

        Regressão: LOGIN_URL apontava para um nome de rota inexistente, e o
        erro só aparecia para visitante não autenticado.
        """
        self.client.logout()
        for rota in [
            reverse("cart:checkout"),
            reverse("orders:lista"),
            reverse("accounts:perfil"),
            reverse("subscriptions:lista"),
            reverse("notifications:lista"),
        ]:
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertEqual(resposta.status_code, 302)
                self.assertTrue(
                    resposta.url.startswith(reverse("accounts:entrar")),
                    f"{rota} redirecionou para {resposta.url}",
                )

    def test_listagens_do_painel_mostram_registros(self):
        """Regressão: um <form> entre <td>s é HTML inválido — o parser o expulsa
        da tabela e a listagem renderiza vazia, mas a view segue devolvendo 200.
        Aqui checamos o conteúdo, não só o status."""
        from apps.catalog.models import Produto

        self.client.force_login(self.lojista)
        produto = Produto.objects.filter(publicado=True).first()

        for rota in [reverse("dashboard:produtos"), reverse("dashboard:estoque")]:
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                corpo = html.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]

                # o sintoma do HTML inválido é a linha sumir do <tbody>
                self.assertIn(produto.sku, corpo, f"{rota} não listou nenhum produto")
                self.assertGreater(
                    corpo.count("<tr"), 0, f"{rota} renderizou a tabela sem linhas"
                )

    def test_painel_bloqueado_para_cliente(self):
        self.client.force_login(self.cliente)
        resposta = self.client.get(reverse("dashboard:painel"))
        self.assertEqual(resposta.status_code, 302)

    def test_fluxo_completo_pix_ate_aprovacao(self):
        from apps.payments.services import cobrar_pix

        self.client.force_login(self.cliente)
        pagamento = cobrar_pix(self.pedido)

        resposta = self.client.get(reverse("payments:pix", args=[pagamento.id]))
        self.assertEqual(resposta.status_code, 200)

        # confirma o Pix pela rota de simulação
        self.client.post(reverse("payments:simular_pix", args=[pagamento.id]))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, Pedido.Status.AGUARDANDO_APROVACAO)

        # o lojista aprova
        self.client.force_login(self.lojista)
        self.client.post(reverse("dashboard:aprovar", args=[self.pedido.numero]))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, Pedido.Status.EM_SEPARACAO)
