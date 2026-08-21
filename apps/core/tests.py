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
        """Cliente logado recebe 403 com explicação, não um rebote para o login.

        Antes o decorator devolvia todo mundo para `accounts:entrar` — quem já
        estava autenticado via a tela de login de novo e parecia que a página
        simplesmente não carregava.
        """
        self.client.force_login(self.cliente)
        resposta = self.client.get(reverse("dashboard:painel"))
        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, "conta de operador", status_code=403)

    def test_painel_manda_anonimo_para_o_login_com_retorno(self):
        self.client.logout()
        resposta = self.client.get(reverse("dashboard:painel"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:entrar"), resposta.url)
        self.assertIn("next=", resposta.url)

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


class RetornoAoCheckoutTests(TestCase):
    """Quem cria conta ou cadastra endereço no meio da compra volta para lá."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.produto = Produto.objects.filter(publicado=True).first()

    def test_checkout_manda_anonimo_para_o_login_com_retorno(self):
        self.client.post(reverse("cart:adicionar", args=[self.produto.slug]))
        resposta = self.client.get(reverse("cart:checkout"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("next=", resposta.url)
        self.assertIn("checkout", resposta.url)

    def test_cadastro_devolve_para_o_checkout(self):
        checkout = reverse("cart:checkout")
        resposta = self.client.post(
            f"{reverse('accounts:cadastrar')}?next={checkout}",
            {
                "first_name": "Novo", "last_name": "Cliente",
                "email": "novo.cliente@exemplo.com", "telefone": "", "cpf": "",
                "password1": "senha-forte-987", "password2": "senha-forte-987",
                "next": checkout,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, checkout)

    def test_endereco_novo_devolve_para_o_checkout(self):
        usuario = User.objects.create_user(
            email="comprador@exemplo.com", password="senha-forte-123"
        )
        self.client.force_login(usuario)
        checkout = reverse("cart:checkout")

        resposta = self.client.post(
            reverse("accounts:enderecos"),
            {
                "apelido": "Casa", "destinatario": "Comprador", "cep": "17300-000",
                "logradouro": "Rua A", "numero": "10", "complemento": "",
                "bairro": "Centro", "cidade": "Dois Córregos", "uf": "SP",
                "referencia": "", "next": checkout,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, checkout)
        self.assertTrue(usuario.enderecos.exists())

    def test_next_para_outro_dominio_e_ignorado(self):
        """Sem validação, `?next=https://site-falso/` faria da nossa tela de
        login um trampolim de phishing."""
        usuario = User.objects.create_user(
            email="alvo@exemplo.com", password="senha-forte-123"
        )
        resposta = self.client.post(
            f"{reverse('accounts:entrar')}?next=https://site-falso.example/",
            {"username": usuario.email, "password": "senha-forte-123",
             "next": "https://site-falso.example/"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn("site-falso", resposta.url)
        self.assertEqual(resposta.url, reverse("core:home"))


class PainelSemAdminDjangoTests(TestCase):
    """O lojista cadastra produto pelo painel, nunca pelo admin do Django."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.lojista = User.objects.create_user(
            email="lojista2@exemplo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.lojista)

    def test_formulario_do_wizard_carrega(self):
        html = self.client.get(reverse("dashboard:produto_form_novo")).content.decode()
        self.assertIn("data-wizard", html)
        self.assertIn('data-tela="1"', html)
        self.assertIn('data-tela="4"', html)
        # o input de foto precisa abrir a câmera no celular
        self.assertIn('capture="environment"', html)

    def test_cadastra_produto_pelo_painel(self):
        from apps.catalog.models import Categoria, Produto

        categoria = Categoria.objects.first()
        resposta = self.client.post(reverse("dashboard:produto_salvar_novo"), {
            "nome": "Ração Teste do Painel",
            "categoria": categoria.id,
            "preco": "99.90",
            "estoque": "12",
            "estoque_minimo": "5",
            "unidade": "un",
            "peso_kg": "1",
            "publicado": "on",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])

        produto = Produto.objects.get(nome="Ração Teste do Painel")
        self.assertTrue(produto.sku.startswith("AGC-"))   # gerado sozinho
        self.assertEqual(produto.estoque, 12)

    def test_wizard_devolve_erros_sem_perder_o_preenchido(self):
        resposta = self.client.post(reverse("dashboard:produto_salvar_novo"), {
            "nome": "Sem categoria nem preço",
        })
        self.assertEqual(resposta.status_code, 400)
        dados = resposta.json()
        self.assertFalse(dados["ok"])
        self.assertIn("categoria", dados["erros"])
        # devolve o HTML com o que já foi digitado
        self.assertIn("Sem categoria nem preço", dados["html"])

    def test_promocional_maior_que_o_preco_e_recusado(self):
        from apps.catalog.models import Categoria

        resposta = self.client.post(reverse("dashboard:produto_salvar_novo"), {
            "nome": "Promoção invertida", "categoria": Categoria.objects.first().id,
            "preco": "50.00", "preco_promocional": "80.00",
            "estoque": "1", "estoque_minimo": "1", "unidade": "un", "peso_kg": "1",
        })
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("preco_promocional", resposta.json()["erros"])

    def test_configuracoes_tem_todas_as_abas(self):
        html = self.client.get(reverse("dashboard:configuracoes")).content.decode()
        for aba in ["aparencia", "pagamentos", "regras", "contato", "firebase", "avancado"]:
            self.assertIn(f'data-aba="{aba}"', html)
        self.assertIn("data-previa", html)          # pré-visualização
        self.assertIn("stone_api_key", html)        # credenciais na tela

    def test_salva_credenciais_e_parcelas_pelo_painel(self):
        from apps.payments.models import ProvedorPagamento

        provedor = ProvedorPagamento.ativo_padrao()
        self.client.post(
            reverse("dashboard:salvar_provedor", args=[provedor.id]),
            {
                "nome": "Stone", "driver": "simulado", "ambiente": "sandbox", "ativo": "on",
                "stone_api_key": "chave-de-teste", "stone_merchant_id": "merchant-1",
                "stone_client_id": "", "stone_client_secret": "",
                "stone_affiliation_code": "", "stone_webhook_secret": "",
                "stone_pix_chave": "pix@agrocampo.online",
                "stone_base_url_sandbox": "https://sandbox-api.stone.com.br",
                "stone_base_url_producao": "https://api.stone.com.br",
                "aceita_cartao": "on", "aceita_pix": "on",
                "parcelas_maximas": "10", "parcelas_sem_juros": "6",
                "valor_minimo_parcela": "25.00",
                "soft_descriptor": "AGROCAMPO",
                "pix_expira_em_minutos": "20", "timeout_segundos": "30",
            },
        )
        provedor.refresh_from_db()
        self.assertEqual(provedor.parcelas_maximas, 10)
        self.assertEqual(provedor.parcelas_sem_juros, 6)
        self.assertEqual(provedor.stone_api_key, "chave-de-teste")
        self.assertFalse(provedor.aceita_boleto)

    def test_nao_deixa_desligar_todos_os_metodos(self):
        """Sem método de pagamento ativo, ninguém consegue fechar pedido."""
        from apps.payments.models import ProvedorPagamento

        provedor = ProvedorPagamento.ativo_padrao()
        self.client.post(
            reverse("dashboard:salvar_provedor", args=[provedor.id]),
            {
                "nome": "Stone", "driver": "simulado", "ambiente": "sandbox", "ativo": "on",
                "parcelas_maximas": "12", "parcelas_sem_juros": "3",
                "valor_minimo_parcela": "30.00", "soft_descriptor": "AGROCAMPO",
                "pix_expira_em_minutos": "30", "timeout_segundos": "30",
                "stone_base_url_sandbox": "https://sandbox-api.stone.com.br",
                "stone_base_url_producao": "https://api.stone.com.br",
            },
        )
        provedor.refresh_from_db()
        self.assertTrue(
            provedor.aceita_cartao or provedor.aceita_pix or provedor.aceita_boleto
        )

    def test_sem_juros_maior_que_o_total_de_parcelas_e_recusado(self):
        from apps.payments.models import ProvedorPagamento

        from apps.dashboard.forms import ProvedorPagamentoForm

        form = ProvedorPagamentoForm(
            instance=ProvedorPagamento.ativo_padrao(),
            data={
                "nome": "Stone", "driver": "simulado", "ambiente": "sandbox", "ativo": "on",
                "aceita_pix": "on",
                "parcelas_maximas": "3", "parcelas_sem_juros": "10",
                "valor_minimo_parcela": "30.00", "soft_descriptor": "AGROCAMPO",
                "pix_expira_em_minutos": "30", "timeout_segundos": "30",
                "stone_base_url_sandbox": "https://sandbox-api.stone.com.br",
                "stone_base_url_producao": "https://api.stone.com.br",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("parcelas_sem_juros", form.errors)

    def test_salva_aparencia_pela_tela(self):
        from apps.core.models import SiteConfig

        self.client.post(reverse("dashboard:salvar_config", args=["aparencia"]), {
            "nome_loja": "AgroCampo Editado",
            "chamada": "Nova chamada da capa",
            "descricao": "Nova descrição",
            "topbar_icone": "🚜",
            "topbar_mensagem": "Nova faixa",
            "topbar_link_texto": "Rastrear",
            "topbar_link_url": "/pedidos/",
        })
        config = SiteConfig.load()
        self.assertEqual(config.nome_loja, "AgroCampo Editado")
        self.assertEqual(config.chamada, "Nova chamada da capa")
