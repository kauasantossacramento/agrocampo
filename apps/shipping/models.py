"""Entrega: cidades atendidas, localidades especiais e cálculo do frete.

A loja entrega numa região concreta, não no Brasil inteiro. Em vez de
adivinhar por CEP, o lojista cadastra as cidades que atende, cada uma com
seu frete, seus dias e seu horário. Localidades de acesso difícil — ilha,
travessia de barco, povoado que o mapa não conhece — entram como um
acréscimo em cima da cidade.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel

DIAS_SEMANA = [
    (0, "Segunda"), (1, "Terça"), (2, "Quarta"), (3, "Quinta"),
    (4, "Sexta"), (5, "Sábado"), (6, "Domingo"),
]


class CidadeQuerySet(models.QuerySet):
    def atendidas(self):
        return self.filter(ativo=True)


class Cidade(TimeStampedModel):
    """Uma cidade onde a loja entrega."""

    nome = models.CharField(max_length=90)
    uf = models.CharField("UF", max_length=2, default="BA")
    sede = models.BooleanField(
        "cidade sede",
        default=False,
        help_text="A cidade da loja. Costuma ter frete e prazo próprios.",
    )

    frete = models.DecimalField(
        "valor do frete", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    frete_gratis_acima_de = models.DecimalField(
        "frete grátis acima de",
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Vazio usa o valor global da loja. 0 desliga o frete grátis aqui.",
    )

    dias_entrega = models.CharField(
        "dias de entrega",
        max_length=20,
        blank=True,
        help_text=(
            "Dias da semana separados por vírgula (0=segunda … 6=domingo). "
            "Ex.: 4 entrega só às sextas. Vazio = todos os dias úteis."
        ),
    )
    horario_a_partir_de = models.TimeField(
        "entregas a partir de",
        null=True, blank=True,
        help_text="Vazio usa o horário padrão da loja.",
    )
    prazo_dias = models.PositiveIntegerField(
        "prazo (dias)", default=1,
        help_text="Dias até a entrega, contados do primeiro dia disponível.",
    )

    observacao = models.CharField(
        max_length=200, blank=True,
        help_text="Aviso exibido ao cliente no checkout.",
    )
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField("atende esta cidade", default=True)

    objects = CidadeQuerySet.as_manager()

    class Meta:
        ordering = ["-sede", "ordem", "nome"]
        unique_together = [("nome", "uf")]
        verbose_name = "cidade atendida"
        verbose_name_plural = "cidades atendidas"

    def __str__(self):
        return f"{self.nome}/{self.uf}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.sede:
            Cidade.objects.exclude(pk=self.pk).update(sede=False)

    # ------------------------------------------------------------ dias
    @property
    def dias(self) -> list[int]:
        """Dias da semana em que entrega. Lista vazia = dias úteis."""
        if not self.dias_entrega.strip():
            return [0, 1, 2, 3, 4]
        dias = []
        for parte in self.dias_entrega.split(","):
            parte = parte.strip()
            if parte.isdigit() and 0 <= int(parte) <= 6:
                dias.append(int(parte))
        return sorted(set(dias)) or [0, 1, 2, 3, 4]

    @property
    def dias_legivel(self) -> str:
        nomes = dict(DIAS_SEMANA)
        dias = self.dias
        if dias == [0, 1, 2, 3, 4]:
            return "de segunda a sexta"
        if len(dias) == 1:
            return f"somente às {nomes[dias[0]].lower()}s"
        return "às " + ", ".join(nomes[d].lower() for d in dias)

    def proxima_entrega(self, a_partir_de: date | None = None) -> date:
        """Primeira data de entrega possível, respeitando os dias e o prazo."""
        referencia = (a_partir_de or date.today()) + timedelta(days=self.prazo_dias)
        dias = self.dias
        for adiante in range(14):
            candidato = referencia + timedelta(days=adiante)
            if candidato.weekday() in dias:
                return candidato
        return referencia

    # ----------------------------------------------------------- frete
    def calcular_frete(self, subtotal: Decimal) -> Decimal:
        """Frete da cidade, já considerando a regra de frete grátis."""
        from apps.core.models import SiteConfig

        limite = self.frete_gratis_acima_de
        if limite is None:
            limite = SiteConfig.load().frete_gratis_acima_de
        if limite and subtotal >= limite:
            return Decimal("0")
        return self.frete


class Localidade(TimeStampedModel):
    """Bairro, povoado ou ilha com custo próprio dentro de uma cidade."""

    cidade = models.ForeignKey(
        Cidade, on_delete=models.CASCADE, related_name="localidades"
    )
    nome = models.CharField(
        max_length=120,
        help_text="Como o cliente conhece o lugar — mesmo que não exista no mapa.",
    )
    frete_adicional = models.DecimalField(
        "acréscimo no frete",
        max_digits=10, decimal_places=2, default=Decimal("10.00"),
        help_text="Somado ao frete da cidade.",
    )
    acesso_por_barco = models.BooleanField(
        "acesso por barco / travessia",
        default=False,
        help_text="Ilhas e localidades que dependem de travessia.",
    )
    prazo_extra_dias = models.PositiveIntegerField(
        "dias a mais no prazo", default=0
    )
    observacao = models.CharField(max_length=200, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["cidade__nome", "nome"]
        unique_together = [("cidade", "nome")]
        verbose_name = "localidade"
        verbose_name_plural = "localidades"

    def __str__(self):
        sufixo = " 🚤" if self.acesso_por_barco else ""
        return f"{self.nome} — {self.cidade.nome}{sufixo}"


class RegraEntrega(TimeStampedModel):
    """Avisos e janelas de entrega exibidos durante a compra.

    Fica separado da cidade porque são recados gerais — "entregamos a partir
    das 15h", "pedidos de sexta saem na segunda" — que o lojista quer poder
    escrever e mudar sozinho.
    """

    class Momento(models.TextChoices):
        CARRINHO = "carrinho", "No carrinho"
        CHECKOUT = "checkout", "Na escolha do endereço"
        PAGAMENTO = "pagamento", "Na tela de pagamento"
        CONFIRMACAO = "confirmacao", "Depois de finalizar"

    titulo = models.CharField(max_length=120)
    mensagem = models.TextField()
    momento = models.CharField(
        max_length=20, choices=Momento.choices, default=Momento.CHECKOUT
    )
    icone = models.CharField(
        max_length=30, default="caminhao",
        help_text="caminhao, relogio, info, alerta, escudo.",
    )
    destaque = models.BooleanField(
        "destacar em amarelo", default=False,
        help_text="Use para avisos que o cliente precisa mesmo ler.",
    )
    cidade = models.ForeignKey(
        Cidade, null=True, blank=True, on_delete=models.CASCADE,
        related_name="regras",
        help_text="Vazio mostra para todas as cidades.",
    )
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "aviso de entrega"
        verbose_name_plural = "avisos de entrega"

    def __str__(self):
        return self.titulo


def calcular_frete(endereco, subtotal: Decimal) -> dict:
    """Frete de um endereço. Devolve valor, prazo e avisos.

    Endereço sem cidade atendida cai no valor global — a loja avisa no
    checkout que precisa confirmar a entrega por WhatsApp em vez de
    silenciosamente cobrar um frete que não sabe cumprir.
    """
    from apps.core.models import SiteConfig

    config = SiteConfig.load()
    cidade = getattr(endereco, "cidade_atendida", None) if endereco else None
    localidade = getattr(endereco, "localidade", None) if endereco else None

    if not cidade:
        return {
            "valor": config.frete_valor,
            "cidade": None,
            "localidade": None,
            "atendida": False,
            "prazo": None,
            "avisos": [
                "Ainda não atendemos esta cidade automaticamente. "
                "Finalize o pedido e a loja confirma a entrega com você."
            ],
        }

    valor = cidade.calcular_frete(subtotal)
    avisos = []

    if localidade and localidade.ativo:
        # o acréscimo entra mesmo com frete grátis: é custo de travessia,
        # não margem sobre o pedido
        valor += localidade.frete_adicional
        if localidade.acesso_por_barco:
            avisos.append(
                f"{localidade.nome} depende de travessia — "
                f"acréscimo de R$ {localidade.frete_adicional:.2f} no frete."
            )
        else:
            avisos.append(
                f"{localidade.nome}: acréscimo de R$ {localidade.frete_adicional:.2f}."
            )

    prazo = cidade.proxima_entrega()
    if localidade and localidade.prazo_extra_dias:
        prazo += timedelta(days=localidade.prazo_extra_dias)

    if not cidade.sede:
        avisos.append(f"Entregamos em {cidade.nome} {cidade.dias_legivel}.")

    horario = cidade.horario_a_partir_de or config.entrega_a_partir_de
    if horario:
        avisos.append(f"As entregas saem a partir das {horario:%H:%M}.")

    if cidade.observacao:
        avisos.append(cidade.observacao)

    return {
        "valor": valor,
        "cidade": cidade,
        "localidade": localidade,
        "atendida": True,
        "prazo": prazo,
        "avisos": avisos,
    }
