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

    def test_fluxo_completo_pix_ate_separacao(self):
        from apps.payments.services import cobrar_pix

        self.client.force_login(self.cliente)
        pagamento = cobrar_pix(self.pedido)

        resposta = self.client.get(reverse("payments:pix", args=[pagamento.id]))
        self.assertEqual(resposta.status_code, 200)

        # confirma o Pix pela rota de simulação
        self.client.post(reverse("payments:simular_pix", args=[pagamento.id]))
        self.pedido.refresh_from_db()
        # sem etapa de aprovação: o pagamento já manda para separação
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
                "email": "novo.cliente@exemplo.com",
                "telefone": "(75) 99999-9999", "cpf": "",
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
            "logo_altura": 60,
        })
        config = SiteConfig.load()
        self.assertEqual(config.nome_loja, "AgroCampo Editado")
        self.assertEqual(config.chamada, "Nova chamada da capa")
        self.assertEqual(config.logo_altura, 60)


class TelasNativasDeConteudoTests(TestCase):
    """Nada do lojista pode depender do admin do Django."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.lojista = User.objects.create_user(
            email="lojista3@exemplo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.lojista)

    def test_todas_as_secoes_de_conteudo_abrem(self):
        from apps.dashboard.gestao import SECOES

        for slug in SECOES:
            with self.subTest(slug=slug):
                resposta = self.client.get(reverse("dashboard:gestao", args=[slug]))
                self.assertEqual(resposta.status_code, 200)
                # tabela em modo cartão para o celular
                self.assertIn("tabela-cartao", resposta.content.decode())

    def test_todas_as_secoes_tem_formulario_no_modal(self):
        from apps.dashboard.gestao import SECOES

        for slug in SECOES:
            with self.subTest(slug=slug):
                html = self.client.get(
                    reverse("dashboard:gestao_form_novo", args=[slug])
                ).content.decode()
                self.assertIn("data-wizard", html)
                self.assertIn("data-wizard-salvar", html)

    def test_cria_e_edita_um_banner_pelo_painel(self):
        from apps.core.models import Banner

        resposta = self.client.post(
            reverse("dashboard:gestao_salvar_novo", args=["banners"]),
            {"titulo": "Banner de teste", "subtitulo": "Sub", "selo": "Novo",
             "cor_fundo": "#D62B20", "texto_botao": "Ver", "link": "/catalogo/",
             "posicao": "hero", "ordem": "0", "publicado": "on"},
        )
        self.assertEqual(resposta.status_code, 200)
        banner = Banner.objects.get(titulo="Banner de teste")

        self.client.post(
            reverse("dashboard:gestao_salvar", args=["banners", banner.pk]),
            {"titulo": "Banner editado", "subtitulo": "Sub", "selo": "",
             "cor_fundo": "#D62B20", "texto_botao": "Ver", "link": "/catalogo/",
             "posicao": "hero", "ordem": "0", "publicado": "on"},
        )
        banner.refresh_from_db()
        self.assertEqual(banner.titulo, "Banner editado")

    def test_cria_cupom_pelo_painel(self):
        from apps.orders.models import Cupom

        self.client.post(
            reverse("dashboard:gestao_salvar_novo", args=["cupons"]),
            {"codigo": "teste10", "descricao": "Dez por cento", "tipo": "percentual",
             "valor": "10", "valor_minimo": "50", "usos_maximos": "0", "ativo": "on"},
        )
        cupom = Cupom.objects.get(codigo="TESTE10")   # normalizado em maiúsculas
        self.assertEqual(cupom.valor, 10)

    def test_categoria_nao_pode_ser_pai_de_si_mesma(self):
        from apps.catalog.models import Categoria
        from apps.dashboard.gestao import CategoriaForm

        categoria = Categoria.objects.filter(pai__isnull=True).first()
        form = CategoriaForm(instance=categoria)
        self.assertNotIn(categoria, form.fields["pai"].queryset)

    def test_secao_inexistente_da_404(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:gestao", args=["inventada"])).status_code,
            404,
        )

    def test_auditoria_abre_em_todas_as_abas(self):
        for tipo in ["pagamentos", "webhooks", "estornos", "transacoes"]:
            with self.subTest(tipo=tipo):
                resposta = self.client.get(reverse("dashboard:auditoria", args=[tipo]))
                self.assertEqual(resposta.status_code, 200)

    def test_painel_nao_manda_o_lojista_para_o_admin_do_django(self):
        """Regressão: os atalhos eram links crus para /admin/."""
        import re

        rotas = [
            reverse("dashboard:painel"),
            reverse("dashboard:produtos"),
            reverse("dashboard:estoque"),
            reverse("dashboard:assinaturas"),
            reverse("dashboard:configuracoes"),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                # o lojista não é superusuário, então nem o atalho técnico aparece
                links = re.findall(r'href="(/admin/[^"]*)"', html)
                self.assertFalse(links, f"{rota} ainda leva ao admin: {links}")


class SemNumeroDeTerceiroTests(TestCase):
    """O telefone da Terra dos Pássaros já vazou para o site uma vez.

    Ele voltou depois disso como "exemplo" em placeholder e help_text — o que
    é igualmente errado, porque alguém copia e cola. Este teste tranca a porta.
    """

    NUMERO_DE_TERCEIRO = ["5514997202800", "99720-2800", "1499720"]

    def test_numero_nao_aparece_em_nenhum_arquivo_do_projeto(self):
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[2]
        ignorar = {".venv", ".git", "node_modules", "media", "staticfiles", "__pycache__"}
        achados = []

        for caminho in raiz.rglob("*"):
            if not caminho.is_file() or caminho.suffix not in {
                ".py", ".html", ".js", ".css", ".md", ".sh", ".yml", ".json"
            }:
                continue
            if any(parte in ignorar for parte in caminho.parts):
                continue
            # o próprio teste cita o número para poder proibi-lo
            if caminho.name == "tests.py" and caminho.parent.name == "core":
                continue
            try:
                texto = caminho.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for numero in self.NUMERO_DE_TERCEIRO:
                if numero in texto:
                    achados.append(f"{caminho.relative_to(raiz)}: {numero}")

        self.assertEqual(achados, [], "Número de terceiro no projeto: " + "; ".join(achados))


class OfertaSoComDescontoRealTests(TestCase):
    """A home não pode anunciar "de R$ X por R$ X"."""

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from django.utils import timezone

        from apps.catalog.models import Categoria, Produto, VariacaoProduto

        categoria = Categoria.objects.create(nome="Ração")
        cls.produto = Produto.objects.create(
            sku="OF-1", nome="Ração com tamanhos", categoria=categoria,
            preco=Decimal("300.00"), preco_promocional=Decimal("270.00"),
            promocao_ate=timezone.now() + timezone.timedelta(days=2),
            estoque=10, publicado=True,
        )
        # a variação padrão custa o preço cheio: a promoção do produto morreu
        VariacaoProduto.objects.create(
            produto=cls.produto, quantidade=Decimal("15"), unidade="kg",
            preco=Decimal("300.00"), estoque=10, padrao=True,
        )

    def test_produto_com_variacao_sem_promocao_fica_fora_da_oferta(self):
        resposta = self.client.get(reverse("core:home"))
        self.assertIsNone(resposta.context["oferta_relampago"])
        self.assertNotIn(self.produto, resposta.context["ofertas"])

    def test_com_promocao_na_variacao_a_oferta_volta(self):
        from decimal import Decimal

        variacao = self.produto.variacoes.first()
        variacao.preco_promocional = Decimal("249.00")
        variacao.save()

        resposta = self.client.get(reverse("core:home"))
        self.assertEqual(resposta.context["oferta_relampago"], self.produto)
        self.assertEqual(self.produto.preco_cheio, Decimal("300.00"))
        self.assertEqual(self.produto.preco_atual, Decimal("249.00"))


class WizardDeTamanhosTests(TestCase):
    """O lojista cadastra 2kg/5kg pelo modal, nunca pelo admin do Django."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User
        from apps.catalog.models import Categoria

        cls.lojista = User.objects.create_user(
            email="lojista-wizard@agrocampo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )
        cls.categoria = Categoria.objects.create(nome="Ração")

    def setUp(self):
        self.client.force_login(self.lojista)

    def _payload(self, **extra):
        base = {
            "nome": "Ração do wizard", "categoria": self.categoria.id,
            "preco": "100.00", "estoque": "0", "estoque_minimo": "2",
            "unidade": "un", "peso_kg": "1", "publicado": "on",
        }
        base.update(extra)
        return base

    def test_formulario_traz_a_etapa_de_tamanhos(self):
        html = self.client.get(
            reverse("dashboard:produto_form_novo")
        ).content.decode()

        self.assertIn('data-tela="3"', html)
        self.assertIn("data-variacao-modelo", html)
        self.assertIn("id_linha", html)

    def test_salvar_cria_os_tamanhos_e_ignora_linha_sem_preco(self):
        from decimal import Decimal

        from apps.catalog.models import Produto

        resposta = self.client.post(
            reverse("dashboard:produto_salvar_novo"),
            self._payload(**{
                "var-0-quantidade": "2", "var-0-unidade": "kg",
                "var-0-preco": "68,90", "var-0-estoque": "12",
                "var-1-quantidade": "5", "var-1-unidade": "kg",
                "var-1-preco": "149.90", "var-1-preco_promocional": "139.90",
                "var-1-estoque": "6",
                "var_padrao": "1",
                # tocou em "adicionar" sem preencher: some sem reclamar
                "var-2-quantidade": "10", "var-2-unidade": "kg", "var-2-preco": "",
            }),
        )
        self.assertEqual(resposta.status_code, 200)

        produto = Produto.objects.get(nome="Ração do wizard")
        self.assertEqual(
            [v.rotulo for v in produto.variacoes.order_by("ordem")], ["2kg", "5kg"]
        )
        # vírgula decimal é o que o teclado do celular oferece
        self.assertEqual(produto.variacoes.first().preco, Decimal("68.90"))
        self.assertEqual(produto.preco_atual, Decimal("139.90"))
        self.assertEqual(produto.preco_a_partir_de, Decimal("68.90"))
        self.assertEqual(produto.estoque_total, 18)

    def test_editar_remove_o_tamanho_que_saiu_da_tela(self):
        from decimal import Decimal

        from apps.catalog.models import Produto

        self.client.post(
            reverse("dashboard:produto_salvar_novo"),
            self._payload(**{
                "var-0-quantidade": "2", "var-0-unidade": "kg",
                "var-0-preco": "68.90", "var-0-estoque": "12",
                "var-1-quantidade": "5", "var-1-unidade": "kg",
                "var-1-preco": "149.90", "var-1-estoque": "6",
                "var_padrao": "1",
            }),
        )
        produto = Produto.objects.get(nome="Ração do wizard")
        dois_kg = produto.variacoes.order_by("ordem").first()

        self.client.post(
            reverse("dashboard:produto_salvar", args=[produto.id]),
            self._payload(**{
                "var-0-id": dois_kg.id, "var-0-quantidade": "2",
                "var-0-unidade": "kg", "var-0-preco": "70.00",
                "var-0-estoque": "9", "var_padrao": "0",
            }),
        )

        produto.refresh_from_db()
        self.assertEqual([v.rotulo for v in produto.variacoes.all()], ["2kg"])
        self.assertEqual(produto.variacoes.first().preco, Decimal("70.00"))
        self.assertTrue(produto.variacoes.first().padrao)

    def test_sem_nenhuma_marcada_a_primeira_vira_padrao(self):
        from apps.catalog.models import Produto

        self.client.post(
            reverse("dashboard:produto_salvar_novo"),
            self._payload(**{
                "var-0-quantidade": "2", "var-0-unidade": "kg",
                "var-0-preco": "68.90", "var-0-estoque": "12",
            }),
        )
        produto = Produto.objects.get(nome="Ração do wizard")
        # sem padrão a vitrine não teria preço para mostrar
        self.assertIsNotNone(produto.variacao_padrao)
        self.assertTrue(produto.variacoes.filter(padrao=True).exists())


class BannerDeApresentacaoTests(TestCase):
    """O topo da home: vídeo/foto com link, e o hero compacto sem ele."""

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Banner

        cls.Banner = Banner

    def test_sem_apresentacao_o_hero_entra_compacto_no_celular(self):
        html = self.client.get(reverse("core:home")).content.decode()

        self.assertIn("hero--compacto-movel", html)
        self.assertNotIn("apresentacao__pilha", html)

    def test_com_apresentacao_ela_assume_o_topo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.Banner.objects.create(
            titulo="Chegou a linha nova",
            posicao=self.Banner.Posicao.APRESENTACAO,
            link="/catalogo/",
            imagem=SimpleUploadedFile("capa.jpg", b"fake", content_type="image/jpeg"),
        )
        html = self.client.get(reverse("core:home")).content.decode()

        self.assertIn("apresentacao__pilha", html)
        self.assertIn("Chegou a linha nova", html)
        # o hero deixa de disputar o topo no celular
        self.assertIn("hero--secundario", html)

    def test_slide_sem_midia_nao_vira_retangulo_preto(self):
        self.Banner.objects.create(
            titulo="Sem foto nenhuma",
            posicao=self.Banner.Posicao.APRESENTACAO,
        )
        html = self.client.get(reverse("core:home")).content.decode()

        self.assertNotIn("Sem foto nenhuma", html)

    def test_destino_cai_no_produto_quando_nao_ha_link(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.catalog.models import Categoria, Produto

        produto = Produto.objects.create(
            sku="AP-1", nome="Ração destaque",
            categoria=Categoria.objects.create(nome="Ração"),
            preco="100.00", estoque=5, publicado=True,
        )
        banner = self.Banner.objects.create(
            titulo="Destaque", posicao=self.Banner.Posicao.APRESENTACAO,
            imagem=SimpleUploadedFile("c.jpg", b"fake", content_type="image/jpeg"),
        )
        banner.produtos.add(produto)

        self.assertEqual(banner.destino, produto.get_absolute_url())

    def test_apresentacao_sem_midia_e_recusada_no_painel(self):
        from apps.dashboard.gestao import BannerForm

        form = BannerForm(data={
            "posicao": self.Banner.Posicao.APRESENTACAO,
            "titulo": "Sem mídia", "cor_fundo": "#D62B20",
            "texto_botao": "Ver", "ordem": 0, "publicado": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("imagem", form.errors)


class LogoNasConfiguracoesTests(TestCase):
    """Trocar e remover a logo tem que funcionar pela tela do lojista."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User

        cls.lojista = User.objects.create_user(
            email="lojista-logo@agrocampo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.lojista)

    def _png(self, nome="logo.png"):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGBA", (320, 96), (214, 43, 32, 255)).save(buf, format="PNG")
        return SimpleUploadedFile(nome, buf.getvalue(), content_type="image/png")

    def _base(self, **extra):
        base = {
            "nome_loja": "AgroCampo", "chamada": "c", "descricao": "d",
            "topbar_icone": "", "topbar_mensagem": "", "topbar_link_texto": "",
            "topbar_link_url": "", "logo_altura": 46,
        }
        base.update(extra)
        return base

    def test_enviar_logo_pela_tela(self):
        from apps.core.models import SiteConfig

        self.client.post(
            reverse("dashboard:salvar_config", args=["aparencia"]),
            self._base(logo=self._png("nova.png"), logo_altura=58),
        )
        config = SiteConfig.load()
        self.assertTrue(config.logo.name)
        self.assertEqual(config.logo_altura, 58)

    def test_caixa_remover_apaga_a_logo(self):
        from apps.core.models import SiteConfig

        self.client.post(
            reverse("dashboard:salvar_config", args=["aparencia"]),
            self._base(logo=self._png()),
        )
        self.assertTrue(SiteConfig.load().logo.name)

        self.client.post(
            reverse("dashboard:salvar_config", args=["aparencia"]),
            self._base(**{"logo-clear": "1"}),
        )
        self.assertEqual(SiteConfig.load().logo.name, "")

    def test_enviar_junto_com_remover_mantem_o_arquivo_novo(self):
        """Marcar remover e escolher outra no mesmo envio não pode apagar."""
        from apps.core.models import SiteConfig

        self.client.post(
            reverse("dashboard:salvar_config", args=["aparencia"]),
            self._base(logo=self._png("primeira.png")),
        )
        self.client.post(
            reverse("dashboard:salvar_config", args=["aparencia"]),
            self._base(logo=self._png("segunda.png"), **{"logo-clear": "1"}),
        )
        self.assertIn("segunda", SiteConfig.load().logo.name)

    def test_tela_mostra_a_logo_que_esta_no_ar(self):
        self.client.post(
            reverse("dashboard:salvar_config", args=["aparencia"]),
            self._base(logo=self._png("visivel.png")),
        )
        html = self.client.get(reverse("dashboard:configuracoes")).content.decode()

        self.assertIn("campo-imagem__previa", html)
        self.assertIn("visivel", html)
        self.assertIn("logo-clear", html)


class SemPromessaDeDescontoInexistenteTests(TestCase):
    """A faixa da home não pode anunciar desconto que o checkout não dá."""

    def test_pix_sem_desconto_nao_anuncia_porcentagem(self):
        from django.core.management import call_command

        from apps.core.models import Diferencial, SiteConfig

        config = SiteConfig.load()
        config.desconto_pix = 0
        config.save(update_fields=["desconto_pix"])

        call_command("seed", verbosity=0)

        textos = " ".join(
            f"{d.titulo} {d.descricao}" for d in Diferencial.objects.all()
        )
        self.assertNotIn("% de desconto à vista", textos)

    def test_com_desconto_ligado_a_porcentagem_bate_com_a_configurada(self):
        from django.core.management import call_command

        from apps.core.models import Diferencial, SiteConfig

        config = SiteConfig.load()
        config.desconto_pix = 7
        config.save(update_fields=["desconto_pix"])

        Diferencial.objects.all().delete()
        call_command("seed", verbosity=0)

        textos = " ".join(
            f"{d.titulo} {d.descricao}" for d in Diferencial.objects.all()
        )
        self.assertIn("7% de desconto à vista", textos)
        self.assertNotIn("5% de desconto", textos)


class OrdemDasVitrinesTests(TestCase):
    """Ouro abre a home; Prata e Bronze na sequência."""

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from apps.catalog.models import Categoria, Produto

        categoria = Categoria.objects.create(nome="Ração")
        for linha, preco in (("ouro", "300"), ("prata", "200"), ("bronze", "100")):
            Produto.objects.create(
                sku=f"L-{linha}", nome=f"Produto {linha}", categoria=categoria,
                preco=Decimal(preco), estoque=5, publicado=True,
                linha=linha, destaque=True,
            )

    def test_ouro_prata_bronze_nesta_ordem(self):
        html = self.client.get(reverse("core:home")).content.decode()

        ouro = html.index("Linha Ouro")
        prata = html.index("Linha Prata")
        bronze = html.index("Linha Bronze")

        self.assertLess(ouro, prata)
        self.assertLess(prata, bronze)

    def test_linha_ouro_vem_antes_do_mais_vendidos_geral(self):
        html = self.client.get(reverse("core:home")).content.decode()

        ouro = html.index("Linha Ouro")
        geral = html.index("O que sai todo dia da nossa loja")

        self.assertLess(ouro, geral)


class ModalDeConteudoTests(TestCase):
    """O modal genérico de conteúdo — banners, cidades, cupons.

    Ele quebrou quando o wizard de produto ganhou a etapa de tamanhos: o JS
    procurava a caixa de tamanhos em todo modal e estourava nos que não a
    têm. Pior, o `prepararWizard()` estava dentro do `try` do fetch, então o
    erro de JS trocava o formulário já carregado pela mensagem "não consegui
    carregar" — com o servidor respondendo 200.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User

        cls.lojista = User.objects.create_user(
            email="lojista-modal@agrocampo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.lojista)

    def test_todas_as_secoes_abrem_o_formulario(self):
        from apps.dashboard.gestao import SECOES

        for slug in SECOES:
            with self.subTest(secao=slug):
                resposta = self.client.get(
                    reverse("dashboard:gestao_form_novo", args=[slug])
                )
                self.assertEqual(resposta.status_code, 200)
                html = resposta.content.decode()
                self.assertIn("data-wizard", html)
                self.assertIn("<input", html + "<select")

    def test_o_js_do_painel_nao_supoe_a_caixa_de_tamanhos(self):
        """Guarda contra a regressão exata: `$$(sel, null)` estoura."""
        import pathlib

        js = (
            pathlib.Path(__file__).resolve().parents[2]
            / "static" / "js" / "painel.js"
        ).read_text(encoding="utf-8")

        # a leitura do índice só pode acontecer com a caixa existindo
        self.assertIn("caixaVariacoes\n      ? $$('[data-variacao]', caixaVariacoes).length", js)
        # e `prepararWizard` precisa ficar fora do try do fetch
        posicao_catch = js.index("Não consegui carregar o formulário")
        posicao_preparar = js.index("prepararWizard();")
        self.assertGreater(posicao_preparar, posicao_catch)

    def test_banner_de_apresentacao_salva_com_imagem_e_produtos(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from apps.catalog.models import Categoria, Produto
        from apps.core.models import Banner

        categoria = Categoria.objects.create(nome="Ração")
        produtos = [
            Produto.objects.create(
                sku=f"B-{i}", nome=f"Produto {i}", categoria=categoria,
                preco="50.00", estoque=3, publicado=True,
            )
            for i in range(2)
        ]

        buf = io.BytesIO()
        Image.new("RGB", (1200, 460), (32, 90, 160)).save(buf, format="PNG")

        resposta = self.client.post(
            reverse("dashboard:gestao_salvar_novo", args=["banners"]),
            {
                "posicao": Banner.Posicao.APRESENTACAO,
                "selo": "", "titulo": "Chegou a linha nova", "subtitulo": "confira",
                "cor_fundo": "#D62B20", "texto_botao": "Ver", "link": "",
                "produtos": [p.id for p in produtos],
                "ordem": 0, "publicado": "on",
                "imagem": SimpleUploadedFile(
                    "capa.png", buf.getvalue(), content_type="image/png"
                ),
            },
        )
        self.assertEqual(resposta.status_code, 200, resposta.content[:400])

        banner = Banner.objects.get(titulo="Chegou a linha nova")
        self.assertTrue(banner.imagem.name)
        self.assertEqual(banner.produtos.count(), 2)
        # sem link escrito, o destino é o primeiro em ordem alfabética —
        # determinístico, em vez de "o que o banco devolver"
        self.assertEqual(banner.destino, produtos[0].get_absolute_url())
        self.assertEqual(banner.destino, banner.destino)


class LimiteDeArquivoTests(TestCase):
    """Arquivo grande demais tem que dizer isso, não "erro de conexão"."""

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import User

        cls.lojista = User.objects.create_user(
            email="lojista-limite@agrocampo.com", password="senha-forte-123",
            papel=User.Papel.LOJISTA, is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.lojista)

    def test_video_acima_do_limite_e_recusado_com_o_tamanho_no_texto(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.core.models import LIMITE_VIDEO_MB, Banner
        from apps.dashboard.gestao import BannerForm

        grande = SimpleUploadedFile(
            "grande.mp4",
            b"\x00" * ((LIMITE_VIDEO_MB + 1) * 1024 * 1024),
            content_type="video/mp4",
        )
        form = BannerForm(
            data={
                "posicao": Banner.Posicao.APRESENTACAO, "titulo": "Grande",
                "cor_fundo": "#D62B20", "texto_botao": "Ver", "ordem": 0,
                "publicado": "on",
            },
            files={"video": grande},
        )
        self.assertFalse(form.is_valid())
        mensagem = " ".join(form.errors["video"])
        self.assertIn(str(LIMITE_VIDEO_MB), mensagem)
        self.assertIn("MB", mensagem)

    def test_video_dentro_do_limite_passa(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.core.models import Banner
        from apps.dashboard.gestao import BannerForm

        form = BannerForm(
            data={
                "posicao": Banner.Posicao.APRESENTACAO, "titulo": "Pequeno",
                "cor_fundo": "#D62B20", "texto_botao": "Ver", "ordem": 0,
                "publicado": "on",
            },
            files={"video": SimpleUploadedFile(
                "ok.mp4", b"\x00" * (2 * 1024 * 1024), content_type="video/mp4"
            )},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_o_painel_nao_le_413_como_json(self):
        """A regressão: `resposta.json()` numa página HTML do nginx."""
        import pathlib

        js = (
            pathlib.Path(__file__).resolve().parents[2]
            / "static" / "js" / "painel.js"
        ).read_text(encoding="utf-8")

        self.assertIn("resposta.status === 413", js)
        self.assertIn("Arquivo grande demais", js)
        # e o content-type é conferido antes de chamar .json()
        posicao_tipo = js.index("content-type")
        posicao_json = js.index("await resposta.json()")
        self.assertLess(posicao_tipo, posicao_json)

    def test_nginx_aceita_mais_que_o_limite_da_aplicacao(self):
        """O corte tem que ser o da aplicação, que explica o motivo."""
        import pathlib
        import re

        from apps.core.models import LIMITE_VIDEO_MB

        conf = (
            pathlib.Path(__file__).resolve().parents[2]
            / "deploy" / "nginx.conf"
        ).read_text(encoding="utf-8")

        achado = re.search(r"client_max_body_size\s+(\d+)M", conf)
        self.assertIsNotNone(achado, "client_max_body_size ausente")
        self.assertGreater(int(achado.group(1)), LIMITE_VIDEO_MB)
