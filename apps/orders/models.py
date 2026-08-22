"""Pedidos: itens congelados no momento da compra, timeline e ciclo de vida.

O fluxo espelha o mockup: o cliente paga, o pedido entra em **análise**, o
lojista confere o estoque e **aprova** ou **recusa**. Na recusa a loja
oferece produtos similares ou o estorno integral.
"""
from decimal import Decimal

from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.core.models import TimeStampedModel


class PedidoQuerySet(models.QuerySet):
    def aguardando_aprovacao(self):
        return self.filter(status=Pedido.Status.AGUARDANDO_APROVACAO)

    def do_usuario(self, usuario):
        return self.filter(usuario=usuario)

    def faturados(self):
        return self.exclude(
            status__in=[
                Pedido.Status.RASCUNHO,
                Pedido.Status.AGUARDANDO_PAGAMENTO,
                Pedido.Status.CANCELADO,
                Pedido.Status.RECUSADO,
            ]
        )


class Pedido(TimeStampedModel):
    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        AGUARDANDO_PAGAMENTO = "aguardando_pagamento", "Aguardando pagamento"
        PAGO = "pago", "Pagamento confirmado"
        # legado: pedidos criados antes de a aprovação ser removida
        AGUARDANDO_APROVACAO = "aguardando_aprovacao", "Aguardando aprovação do lojista"
        APROVADO = "aprovado", "Aprovado"
        EM_SEPARACAO = "em_separacao", "Em separação"
        ENVIADO = "enviado", "Enviado"
        ENTREGUE = "entregue", "Entregue"
        RECUSADO = "recusado", "Recusado pelo lojista"
        CANCELADO = "cancelado", "Cancelado"
        ESTORNADO = "estornado", "Estornado"

    # Transições permitidas. Qualquer outra levanta erro no `mudar_status`.
    TRANSICOES = {
        Status.RASCUNHO: {Status.AGUARDANDO_PAGAMENTO, Status.CANCELADO},
        Status.AGUARDANDO_PAGAMENTO: {Status.PAGO, Status.CANCELADO},
        # Pago vai direto para separação: não há mais etapa de aprovação.
        # Faltando item, o pedido segue e um atendente entra em contato.
        Status.PAGO: {Status.EM_SEPARACAO, Status.CANCELADO, Status.ESTORNADO},
        # Pedidos antigos ainda param nestes dois status — mantidos para que
        # o lojista consiga encerrá-los.
        Status.AGUARDANDO_APROVACAO: {Status.APROVADO, Status.EM_SEPARACAO, Status.RECUSADO},
        Status.APROVADO: {Status.EM_SEPARACAO, Status.CANCELADO},
        Status.EM_SEPARACAO: {Status.ENVIADO, Status.CANCELADO},
        Status.ENVIADO: {Status.ENTREGUE},
        Status.ENTREGUE: set(),
        Status.RECUSADO: {Status.ESTORNADO, Status.CANCELADO},
        Status.CANCELADO: set(),
        Status.ESTORNADO: set(),
    }

    STATUS_ABERTOS = {
        Status.PAGO, Status.AGUARDANDO_APROVACAO, Status.APROVADO,
        Status.EM_SEPARACAO, Status.ENVIADO,
    }

    numero = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    usuario = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="pedidos"
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.RASCUNHO, db_index=True
    )

    # dados do cliente congelados no momento da compra
    nome_cliente = models.CharField(max_length=140)
    email_cliente = models.EmailField()
    telefone_cliente = models.CharField(max_length=20, blank=True)
    endereco_entrega = models.ForeignKey(
        "accounts.Endereco", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos",
    )
    endereco_texto = models.CharField(
        max_length=400, blank=True, help_text="Cópia textual do endereço no momento da compra."
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto_assinatura = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto_pix = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Abatido quando o cliente fecha em Pix. Zerado se trocar de método.",
    )
    frete = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    cupom = models.CharField(max_length=40, blank=True)
    observacoes = models.TextField(blank=True)

    assinatura = models.ForeignKey(
        "subscriptions.Assinatura", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos", help_text="Preenchido quando o pedido nasce de um ciclo.",
    )

    # decisão do lojista
    decidido_por = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_decididos",
    )
    decidido_em = models.DateTimeField(null=True, blank=True)
    contato_pendente = models.BooleanField(
        "atendente precisa falar com o cliente",
        default=False,
        help_text="Algum item saiu sem estoque suficiente na hora da separação.",
    )
    itens_em_falta = models.TextField(
        "itens em falta", blank=True,
        help_text="Preenchido automaticamente quando o estoque não cobre o pedido.",
    )
    motivo_recusa = models.CharField(max_length=250, blank=True)

    codigo_rastreio = models.CharField(max_length=60, blank=True)
    pago_em = models.DateTimeField(null=True, blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    entregue_em = models.DateTimeField(null=True, blank=True)

    objects = PedidoQuerySet.as_manager()

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"

    def __str__(self):
        return f"{self.numero} — {self.nome_cliente}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = self._gerar_numero()
        super().save(*args, **kwargs)

    @staticmethod
    def _gerar_numero():
        ano = timezone.now().strftime("%y")
        while True:
            numero = f"PED-{ano}{get_random_string(6, '0123456789')}"
            if not Pedido.objects.filter(numero=numero).exists():
                return numero

    def get_absolute_url(self):
        return reverse("orders:detalhe", args=[self.numero])

    # ------------------------------------------------------------ totais
    def recalcular(self, salvar=True):
        itens = list(self.itens.all())
        self.subtotal = sum((i.preco_cheio * i.quantidade for i in itens), Decimal("0"))
        self.desconto_assinatura = sum(
            ((i.preco_cheio - i.preco_unitario) * i.quantidade for i in itens), Decimal("0")
        )
        self.total = (
            self.subtotal
            - self.desconto_assinatura
            - self.desconto
            - self.desconto_pix
            + self.frete
        )
        if salvar:
            self.save(
                update_fields=[
                    "subtotal", "desconto_assinatura", "total", "atualizado_em"
                ]
            )
        return self.total

    def aplicar_desconto_pix(self):
        """Abate o percentual de Pix da loja e devolve o valor abatido.

        Fica no pedido, nao no carrinho: o metodo de pagamento so e escolhido
        no checkout, e trocar de metodo tem que desfazer o abatimento.
        """
        from apps.core.models import SiteConfig

        percentual = SiteConfig.load().desconto_pix
        if not percentual:
            return Decimal("0")

        base = self.subtotal - self.desconto_assinatura - self.desconto
        self.desconto_pix = (base * Decimal(percentual) / 100).quantize(Decimal("0.01"))
        self.save(update_fields=["desconto_pix", "atualizado_em"])
        self.recalcular()
        return self.desconto_pix

    def limpar_desconto_pix(self):
        """Desfaz o abatimento quando o cliente muda para cartao ou boleto."""
        if self.desconto_pix:
            self.desconto_pix = Decimal("0")
            self.save(update_fields=["desconto_pix", "atualizado_em"])
            self.recalcular()

    @property
    def quantidade_itens(self):
        return sum(i.quantidade for i in self.itens.all())

    @property
    def tem_recorrencia(self):
        return self.itens.filter(recorrente=True).exists()

    @property
    def pagamento_atual(self):
        return self.pagamentos.order_by("-criado_em").first()

    @property
    def em_aberto(self):
        return self.status in self.STATUS_ABERTOS

    @property
    def pode_ser_estornado(self):
        pagamento = self.pagamento_atual
        return bool(pagamento and pagamento.valor_estornavel > 0 and pagamento.liquidado)

    @property
    def itens_indisponiveis(self):
        """Itens cujo estoque não cobre mais a quantidade pedida."""
        return [i for i in self.itens.select_related("produto") if not i.tem_estoque]

    # ------------------------------------------------------ maquina de estados
    def pode_ir_para(self, novo_status) -> bool:
        return novo_status in self.TRANSICOES.get(self.status, set())

    @transaction.atomic
    def mudar_status(self, novo_status, *, autor=None, titulo="", descricao="", forcar=False):
        if not forcar and not self.pode_ir_para(novo_status):
            raise ValueError(
                f"Transição inválida: {self.get_status_display()} → {novo_status}."
            )
        anterior = self.status
        self.status = novo_status
        campos = ["status", "atualizado_em"]

        agora = timezone.now()
        if novo_status == self.Status.PAGO:
            self.pago_em = agora
            campos.append("pago_em")
        elif novo_status in {self.Status.APROVADO, self.Status.RECUSADO}:
            self.decidido_em = agora
            self.decidido_por = autor
            campos += ["decidido_em", "decidido_por"]
        elif novo_status == self.Status.ENVIADO:
            self.enviado_em = agora
            campos.append("enviado_em")
        elif novo_status == self.Status.ENTREGUE:
            self.entregue_em = agora
            campos.append("entregue_em")

        self.save(update_fields=campos)
        EventoPedido.objects.create(
            pedido=self,
            status_anterior=anterior,
            status_novo=novo_status,
            titulo=titulo or self.get_status_display(),
            descricao=descricao,
            autor=autor,
        )
        return self


class ItemPedido(models.Model):
    """Linha do pedido com preço e nome congelados no momento da compra."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(
        "catalog.Produto", on_delete=models.PROTECT, related_name="itens_pedido"
    )
    variacao = models.ForeignKey(
        "catalog.VariacaoProduto", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="itens_pedido",
    )
    nome_produto = models.CharField(max_length=200)
    variacao_rotulo = models.CharField(
        "apresentação", max_length=30, blank=True,
        help_text="Congelado na compra: 2kg, 500g…",
    )
    sku = models.CharField(max_length=40, blank=True)
    quantidade = models.PositiveIntegerField(default=1)
    preco_unitario = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Preço efetivamente cobrado."
    )
    preco_cheio = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Preço de tabela, antes do desconto."
    )
    recorrente = models.BooleanField(default=False)
    frequencia_dias = models.PositiveIntegerField(null=True, blank=True)
    baixado_do_estoque = models.BooleanField(default=False)

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.descricao_completa}"

    @property
    def descricao_completa(self) -> str:
        if self.variacao_rotulo:
            return f"{self.nome_produto} · {self.variacao_rotulo}"
        return self.nome_produto

    @property
    def foto(self):
        if self.variacao:
            return self.variacao.foto
        return self.produto.foto_principal

    @property
    def total(self):
        return self.preco_unitario * self.quantidade

    @property
    def economia(self):
        return (self.preco_cheio - self.preco_unitario) * self.quantidade

    @property
    def estoque_disponivel(self) -> int:
        return self.variacao.estoque if self.variacao else self.produto.estoque

    @property
    def tem_estoque(self):
        return self.estoque_disponivel >= self.quantidade

    def baixar_estoque(self, pedido_numero):
        """Baixa da variação quando existe, do produto quando não."""
        alvo = self.variacao or self.produto
        alvo.baixar_estoque(self.quantidade, motivo="Venda", pedido=pedido_numero)
        return alvo

    @property
    def rotulo_frequencia(self):
        if not self.recorrente:
            return "Compra única"
        return f"Recorrente · a cada {self.frequencia_dias} dias"


class EventoPedido(TimeStampedModel):
    """Timeline exibida ao cliente e ao lojista."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="eventos")
    status_anterior = models.CharField(max_length=30, blank=True)
    status_novo = models.CharField(max_length=30, blank=True)
    titulo = models.CharField(max_length=140)
    descricao = models.CharField(max_length=300, blank=True)
    autor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="eventos_pedido",
    )
    visivel_para_cliente = models.BooleanField(default=True)

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "evento do pedido"
        verbose_name_plural = "eventos do pedido"

    def __str__(self):
        return f"{self.pedido.numero} · {self.titulo}"


class Cupom(TimeStampedModel):
    class Tipo(models.TextChoices):
        PERCENTUAL = "percentual", "Percentual"
        FIXO = "fixo", "Valor fixo"

    codigo = models.CharField(max_length=40, unique=True)
    descricao = models.CharField(max_length=160, blank=True)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.PERCENTUAL)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valor_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    usos_maximos = models.PositiveIntegerField(default=0, help_text="0 = ilimitado.")
    usos = models.PositiveIntegerField(default=0, editable=False)
    valido_de = models.DateTimeField(null=True, blank=True)
    valido_ate = models.DateTimeField(null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "cupom"
        verbose_name_plural = "cupons"

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.upper().strip()
        super().save(*args, **kwargs)

    def vigente(self):
        agora = timezone.now()
        if not self.ativo:
            return False
        if self.valido_de and agora < self.valido_de:
            return False
        if self.valido_ate and agora > self.valido_ate:
            return False
        if self.usos_maximos and self.usos >= self.usos_maximos:
            return False
        return True

    def calcular(self, subtotal: Decimal) -> Decimal:
        if not self.vigente() or subtotal < self.valor_minimo:
            return Decimal("0")
        if self.tipo == self.Tipo.PERCENTUAL:
            return (subtotal * self.valor / 100).quantize(Decimal("0.01"))
        return min(self.valor, subtotal)
