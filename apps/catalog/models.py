"""Catálogo: categorias hierárquicas, marcas, espécies, produtos e estoque."""
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.core.models import PublicadoQuerySet, SluggedModel, TimeStampedModel

CEM = Decimal("100")


class CategoriaQuerySet(PublicadoQuerySet):
    def raizes(self):
        return self.filter(pai__isnull=True)

    def menu(self):
        return (
            self.publicados()
            .raizes()
            .filter(exibir_no_menu=True)
            .prefetch_related("filhas")
            .order_by("ordem", "nome")
        )


class Categoria(TimeStampedModel, SluggedModel):
    """Categoria hierárquica: Alimentos > Sementes, Pet > Cães, etc."""

    pai = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="filhas",
        verbose_name="categoria pai",
    )
    class Icone(models.TextChoices):
        RACAO = "racao", "Ração e alimentação"
        AVE = "ave", "Aves e pássaros"
        RURAL = "rural", "Rural e fazenda"
        SAUDE = "saude", "Saúde animal"
        ACESSORIO = "acessorio", "Acessórios"
        JARDIM = "jardim", "Casa e jardim"
        CAO = "cao", "Cães"
        GATO = "gato", "Gatos"
        PEIXE = "peixe", "Peixes"
        SEMENTE = "semente", "Sementes"
        PATA = "pata", "Genérico (pata)"

    descricao = models.TextField(blank=True)
    # Emoji renderiza diferente em cada sistema — e some em alguns Android.
    # O ícone virou uma chave para um <symbol> SVG do tema.
    icone = models.CharField(
        "ícone",
        max_length=20,
        blank=True,
        choices=Icone.choices,
        help_text="Ícone vetorial exibido no menu e nos atalhos da home.",
    )
    imagem = models.ImageField(upload_to="categorias/", blank=True)
    ordem = models.PositiveIntegerField(default=0)
    exibir_no_menu = models.BooleanField(default=True)
    destaque_home = models.BooleanField("atalho na home", default=False)
    publicado = models.BooleanField(default=True)

    objects = CategoriaQuerySet.as_manager()

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"

    def __str__(self):
        return f"{self.pai.nome} > {self.nome}" if self.pai else self.nome

    def get_absolute_url(self):
        return reverse("catalog:categoria", args=[self.slug])

    @property
    def icone_svg(self):
        """Chave do <symbol> a usar, sempre válida.

        Os templates montam `href="#c-{{ ... }}"`. Um valor fora das opções
        (emoji de uma base antiga, campo vazio) geraria uma referência para um
        símbolo inexistente — e o ícone some sem nenhum erro visível.
        """
        return self.icone if self.icone in self.Icone.values else "pata"

    @property
    def ramo_ids(self):
        """IDs desta categoria e de todas as descendentes."""
        ids = [self.pk]
        for filha in self.filhas.all():
            ids.extend(filha.ramo_ids)
        return ids


class Marca(TimeStampedModel, SluggedModel):
    logo = models.ImageField(upload_to="marcas/", blank=True)
    descricao = models.TextField(blank=True)
    site = models.URLField(blank=True)
    destaque = models.BooleanField("exibir na vitrine de marcas", default=True)
    ordem = models.PositiveIntegerField(default=0)
    publicado = models.BooleanField(default=True)

    objects = PublicadoQuerySet.as_manager()

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "marca"
        verbose_name_plural = "marcas"

    def get_absolute_url(self):
        return reverse("catalog:marca", args=[self.slug])


class Especie(TimeStampedModel, SluggedModel):
    """Navegação por espécie/animal — canário, calopsita, bovino, cão..."""

    class Grupo(models.TextChoices):
        PASSERIFORME = "passeriforme", "Passeriformes"
        PSITACIDEO = "psitacideo", "Psitacídeos"
        PET = "pet", "Pets"
        RURAL = "rural", "Rural e produção"
        OUTRO = "outro", "Outros"

    grupo = models.CharField(max_length=20, choices=Grupo.choices, default=Grupo.OUTRO)
    imagem = models.ImageField(upload_to="especies/", blank=True)
    credito_imagem = models.CharField(
        "crédito da imagem",
        max_length=250,
        blank=True,
        help_text="Autor e licença — obrigatório para fotos sob Creative Commons.",
    )
    nome_cientifico = models.CharField(max_length=120, blank=True)
    icone = models.CharField(max_length=10, blank=True)
    descricao = models.TextField(blank=True)
    ordem = models.PositiveIntegerField(default=0)
    destaque_home = models.BooleanField(default=False)
    publicado = models.BooleanField(default=True)

    objects = PublicadoQuerySet.as_manager()

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "espécie"
        verbose_name_plural = "espécies"

    def get_absolute_url(self):
        return reverse("catalog:especie", args=[self.slug])


class ProdutoQuerySet(PublicadoQuerySet):
    def disponiveis(self):
        return self.publicados().filter(estoque__gt=0)

    def com_avaliacoes(self):
        return self.annotate(
            nota_media=Avg("avaliacoes__nota", filter=Q(avaliacoes__aprovada=True)),
            total_avaliacoes=Count("avaliacoes", filter=Q(avaliacoes__aprovada=True)),
        )

    def em_promocao(self):
        return self.publicados().filter(preco_promocional__isnull=False)

    def assinaveis(self):
        return self.publicados().filter(permite_assinatura=True)

    def vitrine(self):
        """Seleção padrão de listagem, já com os joins e agregados necessários."""
        return (
            self.publicados()
            .select_related("categoria", "marca")
            .prefetch_related("imagens")
            .com_avaliacoes()
        )


class Produto(TimeStampedModel, SluggedModel):
    class Unidade(models.TextChoices):
        UN = "un", "Unidade"
        KG = "kg", "Quilo"
        L = "l", "Litro"
        PCT = "pct", "Pacote"

    sku = models.CharField("SKU", max_length=40, unique=True)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="produtos"
    )
    marca = models.ForeignKey(
        Marca, on_delete=models.SET_NULL, null=True, blank=True, related_name="produtos"
    )
    especies = models.ManyToManyField(
        Especie, blank=True, related_name="produtos", verbose_name="espécies indicadas"
    )

    resumo = models.CharField(max_length=220, blank=True)
    descricao = models.TextField(blank=True)
    beneficios = models.TextField(
        blank=True, help_text="Um benefício por linha — vira lista na página do produto."
    )
    composicao = models.TextField("composição / tabela nutricional", blank=True)

    preco = models.DecimalField(max_digits=10, decimal_places=2)
    preco_promocional = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    preco_custo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    permite_assinatura = models.BooleanField("disponível para assinatura", default=False)
    desconto_assinatura_proprio = models.PositiveIntegerField(
        "desconto da assinatura (%)",
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(80)],
        help_text=(
            "Deixe vazio para seguir o percentual global da loja "
            "(Configuração da loja › desconto padrão da assinatura). "
            "Preencha só quando este produto precisar de um desconto diferente."
        ),
    )

    unidade = models.CharField(max_length=5, choices=Unidade.choices, default=Unidade.UN)
    peso_kg = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    estoque = models.IntegerField(default=0)
    estoque_minimo = models.PositiveIntegerField(
        default=5, help_text="Abaixo disso o painel emite alerta."
    )

    destaque = models.BooleanField("mais vendido", default=False)
    lancamento = models.BooleanField(default=False)
    publicado = models.BooleanField(default=True)
    vendas = models.PositiveIntegerField(default=0, editable=False)

    promocao_ate = models.DateTimeField(
        null=True, blank=True, help_text="Data-limite da oferta (ativa o contador)."
    )

    objects = ProdutoQuerySet.as_manager()

    class Meta:
        ordering = ["-destaque", "-criado_em"]
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        indexes = [
            models.Index(fields=["publicado", "destaque"]),
            models.Index(fields=["categoria", "publicado"]),
        ]

    def get_absolute_url(self):
        return reverse("catalog:produto", args=[self.slug])

    # ------------------------------------------------------------- precos
    @property
    def promocao_vigente(self):
        if self.preco_promocional is None:
            return False
        if self.promocao_ate and self.promocao_ate < timezone.now():
            return False
        return self.preco_promocional < self.preco

    @property
    def preco_atual(self) -> Decimal:
        """Preço de compra avulsa, já considerando promoção vigente."""
        return self.preco_promocional if self.promocao_vigente else self.preco

    @property
    def desconto_assinatura(self) -> int:
        """Percentual efetivo: o do produto, ou o global da loja.

        Deixar o campo do produto vazio é o caso comum — assim o lojista
        muda o desconto do site inteiro num lugar só.
        """
        if self.desconto_assinatura_proprio is not None:
            return self.desconto_assinatura_proprio

        from apps.core.models import SiteConfig

        return SiteConfig.load().desconto_assinatura_padrao

    @property
    def desconto_assinatura_e_global(self) -> bool:
        return self.desconto_assinatura_proprio is None

    @property
    def preco_assinatura(self) -> Decimal:
        """Preço por ciclo de assinatura."""
        if not self.permite_assinatura:
            return self.preco_atual
        fator = (CEM - Decimal(self.desconto_assinatura)) / CEM
        return (self.preco_atual * fator).quantize(Decimal("0.01"))

    @property
    def economia_assinatura(self) -> Decimal:
        return self.preco_atual - self.preco_assinatura

    @property
    def percentual_desconto(self) -> int:
        if not self.promocao_vigente:
            return 0
        return int(round((self.preco - self.preco_promocional) / self.preco * 100))

    # ------------------------------------------------------------ estoque
    @property
    def em_estoque(self):
        return self.estoque > 0

    @property
    def estoque_baixo(self):
        return 0 < self.estoque <= self.estoque_minimo

    @property
    def rotulo_estoque(self):
        if self.estoque <= 0:
            return "Esgotado"
        if self.estoque_baixo:
            return f"Últimas {self.estoque} unidades"
        return f"Em estoque - {self.estoque} unidades"

    # -------------------------------------------------------------- midia
    @property
    def imagem_principal(self):
        return self.imagens.first()

    @property
    def lista_beneficios(self):
        return [linha.strip() for linha in self.beneficios.splitlines() if linha.strip()]

    def foi_comprado_por(self, usuario) -> bool:
        """True se o usuário tem um pedido entregue/enviado com este produto.

        Só quem recebeu pode avaliar: sem isso a vitrine vira mural aberto.
        """
        if not usuario or not usuario.is_authenticated:
            return False
        from apps.orders.models import Pedido

        return self.itens_pedido.filter(
            pedido__usuario=usuario,
            pedido__status__in=[
                Pedido.Status.APROVADO,
                Pedido.Status.EM_SEPARACAO,
                Pedido.Status.ENVIADO,
                Pedido.Status.ENTREGUE,
            ],
        ).exists()

    def similares(self, limite=4):
        """Produtos da mesma categoria — usados na recusa por falta de estoque."""
        return (
            Produto.objects.vitrine()
            .filter(categoria=self.categoria, estoque__gt=0)
            .exclude(pk=self.pk)[:limite]
        )

    def baixar_estoque(self, quantidade, motivo="", pedido=None):
        """Registra saída de estoque de forma atômica e auditável."""
        Produto.objects.filter(pk=self.pk).update(
            estoque=models.F("estoque") - quantidade,
            vendas=models.F("vendas") + quantidade,
        )
        MovimentoEstoque.objects.create(
            produto=self,
            tipo=MovimentoEstoque.Tipo.SAIDA,
            quantidade=quantidade,
            motivo=motivo,
            pedido_referencia=pedido or "",
        )
        self.refresh_from_db(fields=["estoque", "vendas"])

    def repor_estoque(self, quantidade, motivo="", pedido=None):
        Produto.objects.filter(pk=self.pk).update(estoque=models.F("estoque") + quantidade)
        MovimentoEstoque.objects.create(
            produto=self,
            tipo=MovimentoEstoque.Tipo.ENTRADA,
            quantidade=quantidade,
            motivo=motivo,
            pedido_referencia=pedido or "",
        )
        self.refresh_from_db(fields=["estoque"])


class ProdutoImagem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="imagens")
    imagem = models.ImageField(upload_to="produtos/")
    legenda = models.CharField(max_length=140, blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "imagem do produto"
        verbose_name_plural = "imagens do produto"

    def __str__(self):
        return self.legenda or f"Imagem de {self.produto.nome}"


class MovimentoEstoque(TimeStampedModel):
    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída"
        AJUSTE = "ajuste", "Ajuste manual"

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="movimentos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    quantidade = models.IntegerField()
    motivo = models.CharField(max_length=180, blank=True)
    pedido_referencia = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "movimento de estoque"
        verbose_name_plural = "movimentos de estoque"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.quantidade} · {self.produto.nome}"


class Avaliacao(TimeStampedModel):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="avaliacoes")
    autor = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="avaliacoes"
    )
    nota = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    titulo = models.CharField(max_length=120, blank=True)
    comentario = models.TextField(blank=True)
    aprovada = models.BooleanField(default=True)
    compra_verificada = models.BooleanField(
        "compra verificada",
        default=True,
        help_text="Marcado quando a avaliação veio de quem comprou o produto.",
    )

    class Meta:
        ordering = ["-criado_em"]
        unique_together = [("produto", "autor")]
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"

    def __str__(self):
        return f"{self.produto.nome} - {self.nota}"


class ListaDesejos(TimeStampedModel):
    usuario = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="desejos"
    )
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="desejado_por")

    class Meta:
        unique_together = [("usuario", "produto")]
        ordering = ["-criado_em"]
        verbose_name = "item da lista de desejos"
        verbose_name_plural = "lista de desejos"

    def __str__(self):
        return f"{self.usuario} - {self.produto}"
