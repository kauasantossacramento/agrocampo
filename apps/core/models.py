"""Modelos-base reutilizaveis e conteudo institucional da loja."""
from decimal import Decimal

from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class SluggedModel(models.Model):
    """Gera slug a partir de `slug_source` quando nao informado."""

    slug_source = "nome"

    nome = models.CharField("nome", max_length=180)
    slug = models.SlugField("slug", max_length=200, unique=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(getattr(self, self.slug_source) or "")[:190] or "item"
            candidato, i = base, 2
            Model = type(self)
            while Model.objects.filter(slug=candidato).exclude(pk=self.pk).exists():
                sufixo = f"-{i}"
                candidato = f"{base[: 190 - len(sufixo)]}{sufixo}"
                i += 1
            self.slug = candidato
        super().save(*args, **kwargs)


class PublicadoQuerySet(models.QuerySet):
    def publicados(self):
        return self.filter(publicado=True)


class SiteConfig(TimeStampedModel):
    """Configuracao editavel da loja (singleton, pk=1)."""

    nome_loja = models.CharField(max_length=120, default="Veterinária AgroCampo")
    chamada = models.CharField(
        max_length=200,
        default="Tudo para o campo e para quem você ama cuidar.",
        help_text="Frase principal exibida no hero da home.",
    )
    descricao = models.TextField(
        default=(
            "Ração, suplementos e equipamentos rurais com entrega rápida — e "
            "assinatura recorrente para nunca faltar o essencial."
        )
    )
    logo = models.ImageField(upload_to="site/", blank=True)
    logo_claro = models.ImageField(
        upload_to="site/", blank=True, help_text="Versão para fundos escuros."
    )
    favicon = models.ImageField(upload_to="site/", blank=True)

    imagem_capa = models.ImageField(
        "imagem de capa",
        upload_to="site/",
        blank=True,
        help_text=(
            "Figura recortada exibida no banner da home. Use PNG com fundo "
            "transparente. Vale como padrão quando o banner não tem imagem própria."
        ),
    )

    # ------------------------------------------------------------- topo
    topbar_mensagem = models.CharField(
        "mensagem da faixa do topo",
        max_length=120,
        blank=True,
        default="Frete facilitado para toda a zona rural",
        help_text="Texto em destaque na barra escura acima do cabeçalho. Vazio esconde a barra.",
    )
    topbar_icone = models.CharField(
        "emoji da faixa do topo", max_length=8, blank=True, default="🚚"
    )
    topbar_link_texto = models.CharField(
        max_length=40, blank=True, default="Rastrear meu pedido"
    )
    topbar_link_url = models.CharField(max_length=200, blank=True, default="/pedidos/")

    telefone = models.CharField(max_length=40, blank=True)
    whatsapp = models.CharField(
        max_length=40, blank=True, help_text="Só números com DDI, ex.: 5575900000000"
    )
    email_contato = models.EmailField(blank=True)
    endereco = models.CharField(max_length=250, blank=True)
    cidade_uf = models.CharField("cidade / UF", max_length=90, blank=True)
    cep = models.CharField("CEP", max_length=9, blank=True)
    cnpj = models.CharField(max_length=20, blank=True)
    horario_atendimento = models.CharField(
        max_length=160,
        blank=True,
        default="Seg a sex, 8h às 18h · Sáb, 8h às 12h",
    )

    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    youtube = models.URLField(blank=True)

    rodape_sobre = models.TextField(
        "texto do rodapé",
        blank=True,
        help_text="Se vazio, usa a descrição da loja.",
    )

    ano_fundacao = models.PositiveIntegerField(
        "ano de fundação",
        default=2012,
        help_text="Conforme o CNPJ. O site calcula os anos de mercado a partir daqui.",
    )
    logo_altura = models.PositiveIntegerField(
        "altura da logo (px)",
        default=46,
        validators=[MinValueValidator(24), MaxValueValidator(96)],
        help_text="No celular ela encolhe sozinha. Entre 24 e 96.",
    )

    # ------------------------------------------------------- entrega
    entrega_a_partir_de = models.TimeField(
        "entregas a partir de",
        null=True, blank=True,
        help_text="Horário padrão. Cada cidade pode ter o seu.",
    )
    aviso_entrega = models.TextField(
        "aviso geral de entrega",
        blank=True,
        help_text="Aparece no carrinho e no checkout.",
    )

    # -------------------------------------------------- balão do WhatsApp
    whatsapp_flutuante = models.BooleanField(
        "botão flutuante do WhatsApp", default=True
    )
    whatsapp_mensagem = models.CharField(
        max_length=200,
        blank=True,
        default="Olá! Vim pelo site e gostaria de tirar uma dúvida.",
        help_text="Texto já preenchido quando o cliente abre a conversa.",
    )

    # ------------------------------------------ vitrines por linha
    vitrine_ouro_titulo = models.CharField(
        max_length=60, blank=True, default="Mais vendidos — Linha Ouro"
    )
    vitrine_prata_titulo = models.CharField(
        max_length=60, blank=True, default="Mais vendidos — Linha Prata"
    )
    vitrine_bronze_titulo = models.CharField(
        max_length=60, blank=True, default="Mais vendidos — Linha Bronze"
    )
    vitrine_ouro_ativa = models.BooleanField(default=True)
    vitrine_prata_ativa = models.BooleanField(default=True)
    vitrine_bronze_ativa = models.BooleanField(default=True)

    # ------------------------------------------------------------- PWA
    pwa_convite_ativo = models.BooleanField(
        "convidar a instalar o app",
        default=True,
        help_text="Mostra o convite de instalação para quem ainda não instalou.",
    )
    pwa_convite_segundos = models.PositiveIntegerField(
        "esperar antes de convidar (segundos)",
        default=30,
        help_text="Tempo de navegação antes de o convite aparecer.",
    )
    pwa_convite_texto = models.CharField(
        max_length=160,
        blank=True,
        default="Instale o app da AgroCampo e compre em dois toques.",
    )

    # --------------------------------------------- Firebase (notificações push)
    # Espaços reservados: enquanto vazios, o push fica desligado e o site
    # opera normalmente com as notificações in-app.
    firebase_api_key = models.CharField("Firebase · apiKey", max_length=200, blank=True)
    firebase_auth_domain = models.CharField("Firebase · authDomain", max_length=200, blank=True)
    firebase_project_id = models.CharField("Firebase · projectId", max_length=120, blank=True)
    firebase_storage_bucket = models.CharField("Firebase · storageBucket", max_length=200, blank=True)
    firebase_messaging_sender_id = models.CharField(
        "Firebase · messagingSenderId", max_length=80, blank=True
    )
    firebase_app_id = models.CharField("Firebase · appId", max_length=200, blank=True)
    firebase_vapid_key = models.CharField(
        "Firebase · chave VAPID (par de chaves da Web Push)",
        max_length=250,
        blank=True,
        help_text="Console do Firebase › Cloud Messaging › Certificados push da Web.",
    )
    firebase_service_account = models.TextField(
        "Firebase · JSON da conta de serviço",
        blank=True,
        help_text="Credencial do Admin SDK, usada pelo servidor para disparar o push. "
                  "Guardada só no banco e nunca exposta ao navegador.",
    )

    blog_ativo = models.BooleanField(
        "blog ativo",
        default=True,
        help_text="Desmarque para esconder o blog do menu, do rodapé e da home. "
                  "As URLs passam a responder 404.",
    )
    frete_valor = models.DecimalField(
        "valor do frete",
        max_digits=10,
        decimal_places=2,
        default=Decimal("24.90"),
        help_text="Cobrado quando o pedido não atinge o mínimo do frete grátis.",
    )
    frete_gratis_acima_de = models.DecimalField(
        "frete grátis acima de",
        max_digits=10,
        decimal_places=2,
        default=199,
        help_text="Deixe 0 para nunca dar frete grátis.",
    )
    desconto_assinatura_padrao = models.PositiveIntegerField(
        "desconto padrão da assinatura (%)", default=10
    )
    desconto_pix = models.PositiveIntegerField(
        "desconto no Pix (%)",
        default=0,
        help_text=(
            "Abatido do total quando o cliente escolhe Pix. Só prometa o que "
            "for cumprir: o valor aparece no checkout e é cobrado a menos."
        ),
    )

    class Meta:
        verbose_name = "configuração da loja"
        verbose_name_plural = "configuração da loja"

    def __str__(self):
        return self.nome_loja

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def texto_rodape(self):
        return self.rodape_sobre or self.descricao

    @property
    def endereco_completo(self):
        partes = [p for p in (self.endereco, self.cidade_uf, self.cep) if p]
        return " · ".join(partes)

    @property
    def anos_de_mercado(self):
        """Calculado, nunca digitado: um número fixo envelhece errado."""
        from django.utils import timezone

        return max(0, timezone.localdate().year - self.ano_fundacao)

    @property
    def firebase_configurado(self):
        """True quando dá para inicializar o SDK no navegador."""
        return bool(
            self.firebase_api_key
            and self.firebase_project_id
            and self.firebase_messaging_sender_id
            and self.firebase_app_id
        )

    @property
    def firebase_web_config(self):
        """Config que vai para o cliente. A conta de serviço nunca entra aqui."""
        if not self.firebase_configurado:
            return None
        return {
            "apiKey": self.firebase_api_key,
            "authDomain": self.firebase_auth_domain,
            "projectId": self.firebase_project_id,
            "storageBucket": self.firebase_storage_bucket,
            "messagingSenderId": self.firebase_messaging_sender_id,
            "appId": self.firebase_app_id,
        }

    @property
    def whatsapp_url(self):
        numero = "".join(c for c in self.whatsapp if c.isdigit())
        return f"https://wa.me/{numero}" if numero else ""

    @property
    def whatsapp_url_com_mensagem(self):
        from urllib.parse import quote

        base = self.whatsapp_url
        if not base:
            return ""
        return f"{base}?text={quote(self.whatsapp_mensagem)}" if self.whatsapp_mensagem else base

    def vitrines_por_linha(self):
        """Config das três vitrines, na ordem em que aparecem na home."""
        from apps.catalog.models import Produto

        return [
            {"linha": Produto.Linha.OURO, "titulo": self.vitrine_ouro_titulo,
             "ativa": self.vitrine_ouro_ativa, "classe": "ouro"},
            {"linha": Produto.Linha.PRATA, "titulo": self.vitrine_prata_titulo,
             "ativa": self.vitrine_prata_ativa, "classe": "prata"},
            {"linha": Produto.Linha.BRONZE, "titulo": self.vitrine_bronze_titulo,
             "ativa": self.vitrine_bronze_ativa, "classe": "bronze"},
        ]


class Banner(TimeStampedModel):
    class Posicao(models.TextChoices):
        HERO = "hero", "Carrossel principal"
        FAIXA = "faixa", "Faixa promocional"
        SECUNDARIO = "secundario", "Banner secundário"
        PRODUTOS = "produtos", "Faixa de produtos (fotos com link)"
        APRESENTACAO = "apresentacao", "Apresentação (vídeo ou foto no topo)"

    titulo = models.CharField(max_length=140)
    subtitulo = models.CharField(max_length=220, blank=True)
    selo = models.CharField(max_length=60, blank=True, help_text="Etiqueta acima do título.")
    imagem = models.ImageField(upload_to="banners/", blank=True)
    video = models.FileField(
        "vídeo",
        upload_to="banners/video/",
        blank=True,
        validators=[FileExtensionValidator(["mp4", "webm", "ogv"])],
        help_text=(
            "MP4 ou WebM, curto e sem som — ele toca sozinho e em silêncio. "
            "Acima de ~5 MB a página fica lenta no 4G."
        ),
    )
    cor_fundo = models.CharField(max_length=20, default="#D62B20")
    texto_botao = models.CharField(max_length=40, blank=True, default="Ver catálogo")
    link = models.CharField(max_length=300, blank=True)
    posicao = models.CharField(max_length=20, choices=Posicao.choices, default=Posicao.HERO)
    produtos = models.ManyToManyField(
        "catalog.Produto",
        blank=True,
        related_name="banners",
        verbose_name="produtos da faixa",
        help_text=(
            "Só para a faixa de produtos: cada foto vira um link direto para "
            "o produto."
        ),
    )
    ordem = models.PositiveIntegerField(default=0)
    publicado = models.BooleanField(default=True)

    objects = PublicadoQuerySet.as_manager()

    class Meta:
        ordering = ["ordem", "-criado_em"]
        verbose_name = "banner"
        verbose_name_plural = "banners"

    def __str__(self):
        return self.titulo

    @property
    def tem_midia(self) -> bool:
        return bool(self.video or self.imagem)

    @property
    def destino(self) -> str:
        """Para onde o slide leva. Vazio não vira link — clique morto irrita.

        Sem link escrito, cai no produto vinculado. Com vários vinculados a
        escolha é por ordem alfabética, e não "o que eu marquei primeiro":
        a ordem de marcação não fica guardada em lugar nenhum, e deixar o
        banco decidir daria um destino diferente a cada consulta.
        """
        if self.link:
            return self.link
        primeiro = self.produtos.filter(publicado=True).order_by("nome").first()
        return primeiro.get_absolute_url() if primeiro else ""

    @property
    def produtos_visiveis(self):
        """Só produtos publicados: um link para produto fora do ar é um beco."""
        return self.produtos.filter(publicado=True).prefetch_related("imagens")


class Diferencial(TimeStampedModel):
    """Blocos de confiança exibidos na home (30 anos, entrega, etc.)."""

    titulo = models.CharField(max_length=80)
    descricao = models.CharField(max_length=160, blank=True)
    icone = models.CharField(
        max_length=40,
        default="truck",
        help_text="Nome do ícone SVG: truck, shield, refresh, zap, award, leaf.",
    )
    ordem = models.PositiveIntegerField(default=0)
    publicado = models.BooleanField(default=True)

    objects = PublicadoQuerySet.as_manager()

    class Meta:
        ordering = ["ordem"]
        verbose_name = "diferencial"
        verbose_name_plural = "diferenciais"

    def __str__(self):
        return self.titulo


class Pagina(TimeStampedModel, SluggedModel):
    """Página institucional: quem somos, trocas, privacidade, entregas, FAQ."""

    slug_source = "nome"
    resumo = models.CharField(max_length=220, blank=True)
    conteudo = models.TextField(help_text="Aceita HTML simples.")
    publicado = models.BooleanField(default=True)
    ordem_rodape = models.PositiveIntegerField(
        default=0, help_text="0 esconde do rodapé."
    )

    objects = PublicadoQuerySet.as_manager()

    class Meta:
        ordering = ["ordem_rodape", "nome"]
        verbose_name = "página institucional"
        verbose_name_plural = "páginas institucionais"

    def get_absolute_url(self):
        return reverse("core:pagina", args=[self.slug])


class AssinanteNewsletter(TimeStampedModel):
    email = models.EmailField(unique=True)
    nome = models.CharField(max_length=120, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "assinante da newsletter"
        verbose_name_plural = "assinantes da newsletter"

    def __str__(self):
        return self.email
