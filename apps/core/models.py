"""Modelos-base reutilizaveis e conteudo institucional da loja."""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
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
        default=64,
        validators=[MinValueValidator(24), MaxValueValidator(120)],
        help_text="No celular ela encolhe sozinha. Entre 24 e 120.",
    )

    # ------------------------------------------------------ estilo da home
    # Dois desenhos convivem para o lojista poder voltar sem deploy:
    # "classico" é o original (hero com texto grande sobre vermelho);
    # "vitrine" segue a estrutura de lojas como a Terra dos Pássaros —
    # barra superior fixa, menu escuro, carrossel de imagens, seções com
    # título + linha + "ver todos".
    class LayoutHome(models.TextChoices):
        VITRINE = "vitrine", "Vitrine (carrossel de imagens, menu escuro)"
        CLASSICO = "classico", "Clássico (hero com texto sobre vermelho)"

    layout_home = models.CharField(
        "estilo da home",
        max_length=12, choices=LayoutHome.choices, default=LayoutHome.VITRINE,
        help_text="Trocar aqui muda o cabeçalho e a ordem dos blocos da home na hora.",
    )

    # -------------------------------------------------------------- capa
    # Dois blocos podem abrir a home: o carrossel de slides (cartazes com
    # link) e a apresentação (vídeo/foto grande). O lojista liga um, outro
    # ou os dois. Por padrão só o carrossel.
    capa_slides_ativa = models.BooleanField(
        "mostrar o carrossel de slides", default=True,
    )
    capa_apresentacao_ativa = models.BooleanField(
        "mostrar o banner de apresentação (vídeo/foto)", default=False,
        help_text="O bloco grande de vídeo. Desligado, o carrossel abre a home sozinho.",
    )

    # ---------------------------------------------- ordem das seções da home
    # Chaves separadas por vírgula, na ordem em que os blocos aparecem. O
    # painel edita com setas; quem faltar aqui entra no fim, quem não existir
    # é ignorado — assim uma seção nova nunca some por causa de config velha.
    home_ordem = models.CharField(
        "ordem das seções da home", max_length=400, blank=True,
        default="sucessos,ouro,prata,bronze,especies,categorias,faixas,oferta,"
                "promocoes,destaques,lancamentos,assinatura,porque,blog,newsletter,marcas",
    )

    # ------------------------------------------------------- entrega
    entrega_a_partir_de = models.TimeField(
        "entregas a partir de",
        null=True, blank=True,
        help_text="Horário padrão. Cada cidade pode ter o seu.",
    )
    entrega_hora_limite = models.TimeField(
        "pedidos até (hora de corte)",
        null=True, blank=True, default=datetime.time(14, 0),
        help_text=(
            "Pedido pago depois desta hora conta como do dia seguinte. "
            "Vazio: o dia do pedido conta inteiro."
        ),
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


    # ------------------------------------ WhatsApp automático (WhatsApp Web)
    # Interruptor do envio automático de avisos de pedido pelo serviço
    # `whatsapp` do compose (whatsapp-web.js). O endereço e o token do
    # serviço vêm do ambiente, porque são infraestrutura; aqui fica só a
    # decisão do lojista de ligar ou não.
    whatsapp_auto_ativo = models.BooleanField(
        "enviar avisos de pedido pelo WhatsApp automaticamente",
        default=False,
        help_text=(
            "Usa uma sessão do WhatsApp Web controlada pelo servidor. Esse "
            "formato não é oficial e o número pode ser banido pelo WhatsApp."
        ),
    )

    # ------------------------------------------ assistente virtual (Silvinha)
    assistente_ativo = models.BooleanField("assistente virtual ligada", default=False)
    assistente_nome = models.CharField(
        "nome da assistente", max_length=40, default="Silvinha"
    )
    assistente_imagem = models.ImageField(
        "foto / avatar", upload_to="site/", blank=True,
        help_text="Quadrada, de preferência. Sem imagem aparece a inicial do nome.",
    )
    assistente_boas_vindas = models.CharField(
        "primeira mensagem", max_length=200, blank=True,
        default="Oi! Eu sou a Silvinha, da AgroCampo. Posso ajudar a escolher um produto ou tirar dúvida sobre entrega?",
    )
    assistente_instrucoes = models.TextField(
        "orientações extras", blank=True,
        help_text=(
            "O que ela deve saber ou evitar. Ex.: 'não prometa prazo para "
            "cidades fora da lista', 'sugira ração Golden para cães adultos'."
        ),
    )
    gemini_api_key = models.CharField(
        "Gemini · chave da API", max_length=200, blank=True,
        help_text="aistudio.google.com › Get API key. Fica só no servidor.",
    )
    gemini_modelo = models.CharField(
        "Gemini · modelo", max_length=60, default="gemini-2.5-flash", blank=True,
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
    assinatura_visivel = models.BooleanField(
        "mostrar a assinatura na loja", default=True,
        help_text="Desligado, some do menu, dos cards, do produto e da home. "
                  "As assinaturas já feitas continuam sendo processadas.",
    )
    desconto_assinatura_padrao = models.PositiveIntegerField(
        "desconto padrão da assinatura (%)", default=0,
        help_text="0 desliga o desconto: a assinatura vira só comodidade de entrega.",
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

    # (chave, rótulo no painel) — a ordem aqui é a padrão
    SECOES_HOME = [
        ("sucessos", "Maiores sucessos"),
        ("ouro", "Linha Ouro"),
        ("prata", "Linha Prata"),
        ("bronze", "Linha Bronze"),
        ("especies", "Navegue pelo seu animal"),
        ("categorias", "Compre por categoria"),
        ("faixas", "Faixas de produtos (banners com fotos)"),
        ("oferta", "Oferta especial do dia"),
        ("promocoes", "Em promoção"),
        ("destaques", "Ofertas em destaque (4 cartazes)"),
        ("lancamentos", "Lançamentos do mês"),
        ("assinatura", "Assinatura"),
        ("porque", "Por que comprar"),
        ("blog", "Blog"),
        ("newsletter", "Newsletter"),
        ("marcas", "Nossas marcas"),
    ]

    def secoes_home(self) -> list[str]:
        """Chaves na ordem escolhida, completadas com as que faltarem."""
        validas = [c for c, _ in self.SECOES_HOME]
        escolhidas = [c.strip() for c in (self.home_ordem or "").split(",") if c.strip() in validas]
        vistas = set()
        ordem = []
        for c in escolhidas + validas:
            if c not in vistas:
                vistas.add(c)
                ordem.append(c)
        return ordem

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


# O nginx corta em 80 MB e devolve uma página HTML de erro, que o painel não
# consegue interpretar — vira "erro de conexão". Barrar antes, aqui e no
# navegador, é o que dá uma mensagem útil ao lojista.
LIMITE_VIDEO_MB = 60
ALERTA_VIDEO_MB = 8
LIMITE_IMAGEM_MB = 10


def _validar_tamanho(arquivo, limite_mb, tipo):
    if arquivo and arquivo.size > limite_mb * 1024 * 1024:
        raise ValidationError(
            f"{tipo} tem {arquivo.size / 1024 / 1024:.1f} MB e o limite é "
            f"{limite_mb} MB. Comprima o arquivo e envie de novo."
        )


def validar_tamanho_video(arquivo):
    _validar_tamanho(arquivo, LIMITE_VIDEO_MB, "O vídeo")


def validar_tamanho_imagem(arquivo):
    _validar_tamanho(arquivo, LIMITE_IMAGEM_MB, "A imagem")


class Banner(TimeStampedModel):
    class Posicao(models.TextChoices):
        HERO = "hero", "Carrossel principal"
        FAIXA = "faixa", "Faixa promocional"
        SECUNDARIO = "secundario", "Oferta em destaque (cartaz na home)"
        PRODUTOS = "produtos", "Faixa de produtos (fotos com link)"
        APRESENTACAO = "apresentacao", "Vídeo ou foto de apresentação (entra no carrossel)"

    titulo = models.CharField(max_length=140)
    subtitulo = models.CharField(max_length=220, blank=True)
    selo = models.CharField(max_length=60, blank=True, help_text="Etiqueta acima do título.")
    imagem = models.ImageField(
        upload_to="banners/", blank=True,
        validators=[validar_tamanho_imagem],
    )
    video = models.FileField(
        "vídeo",
        upload_to="banners/video/",
        blank=True,
        validators=[
            FileExtensionValidator(["mp4", "webm", "ogv"]),
            validar_tamanho_video,
        ],
        help_text=(
            f"MP4 ou WebM, curto e sem som — ele toca sozinho e em silêncio. "
            f"Até {LIMITE_VIDEO_MB} MB; acima de {ALERTA_VIDEO_MB} MB a página "
            f"fica lenta para quem abre no 4G."
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


class PromocaoDestaque(TimeStampedModel):
    """Bloco de promoção que o lojista liga por um período, numa posição da home.

    Diferente do banner, ele tem começo e fim e sabe onde entrar: "depois de
    Maiores sucessos", "depois da Linha Ouro"… Passou o prazo, some sozinho.
    """

    titulo = models.CharField(max_length=120)
    texto = models.TextField(blank=True, help_text="Condições, validade, o que quiser dizer.")
    imagem = models.ImageField(upload_to="promocoes/", blank=True, help_text="Opcional.")
    produto = models.ForeignKey(
        "catalog.Produto", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="promocoes_destaque",
        help_text="Opcional: puxa a foto e o link do produto quando não houver imagem/link próprios.",
    )
    link = models.CharField(max_length=300, blank=True)
    texto_botao = models.CharField(max_length=40, blank=True, default="Aproveitar")
    cor_fundo = models.CharField(max_length=20, default="#D62B20")
    inicio = models.DateTimeField("visível a partir de")
    fim = models.DateTimeField("visível até")
    posicao = models.CharField(
        "posição na home", max_length=20, default="sucessos",
        help_text="Aparece logo depois desta seção.",
    )
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "-inicio"]
        verbose_name = "promoção em destaque"
        verbose_name_plural = "promoções em destaque"

    def __str__(self):
        return self.titulo

    @property
    def vigente(self) -> bool:
        from django.utils import timezone

        agora = timezone.now()
        return self.ativo and self.inicio <= agora <= self.fim

    @property
    def destino(self) -> str:
        if self.link:
            return self.link
        if self.produto_id:
            return self.produto.get_absolute_url()
        return "/catalogo/?promocao=1"

    @property
    def foto(self):
        if self.imagem:
            return self.imagem
        if self.produto_id:
            return self.produto.foto_principal
        return None
