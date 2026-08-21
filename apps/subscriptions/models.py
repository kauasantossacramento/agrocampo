"""Assinaturas recorrentes — o diferencial da AgroCampo.

Cada assinatura tem uma cadência (30/60/90 dias) e gera um `CicloAssinatura`
por entrega. O ciclo cobra o cartão tokenizado na Stone e cria um pedido
normal, que segue o mesmo fluxo de aprovação do lojista.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Assinatura(TimeStampedModel):
    class Status(models.TextChoices):
        ATIVA = "ativa", "Ativa"
        PAUSADA = "pausada", "Pausada"
        CANCELADA = "cancelada", "Cancelada"
        INADIMPLENTE = "inadimplente", "Pagamento pendente"

    FREQUENCIAS = [(30, "A cada 30 dias"), (60, "A cada 60 dias"), (90, "A cada 90 dias")]

    usuario = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="assinaturas"
    )
    produto = models.ForeignKey(
        "catalog.Produto", on_delete=models.PROTECT, related_name="assinaturas"
    )
    quantidade = models.PositiveIntegerField(default=1)
    frequencia_dias = models.PositiveIntegerField(choices=FREQUENCIAS, default=30)

    preco_unitario = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Preço congelado no momento da assinatura.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVA)

    endereco_entrega = models.ForeignKey(
        "accounts.Endereco", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assinaturas",
    )
    cartao = models.ForeignKey(
        "payments.CartaoTokenizado", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assinaturas",
        help_text="Cartão tokenizado usado nas cobranças recorrentes.",
    )

    proxima_entrega = models.DateField(db_index=True)
    pausada_ate = models.DateField(null=True, blank=True)
    cancelada_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.CharField(max_length=200, blank=True)
    falhas_consecutivas = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "assinatura"
        verbose_name_plural = "assinaturas"

    def __str__(self):
        return f"{self.produto.nome} · {self.get_frequencia_dias_display()}"

    def save(self, *args, **kwargs):
        if not self.proxima_entrega:
            self.proxima_entrega = timezone.localdate() + timedelta(days=self.frequencia_dias)
        super().save(*args, **kwargs)

    @property
    def total_por_ciclo(self) -> Decimal:
        return self.preco_unitario * self.quantidade

    @property
    def economia_por_ciclo(self) -> Decimal:
        return (self.produto.preco_atual - self.preco_unitario) * self.quantidade

    @property
    def ativa(self):
        return self.status == self.Status.ATIVA

    @property
    def vencida(self):
        return self.ativa and self.proxima_entrega <= timezone.localdate()

    def pular_ciclo(self):
        """Adia uma entrega sem cancelar a assinatura."""
        self.proxima_entrega += timedelta(days=self.frequencia_dias)
        self.save(update_fields=["proxima_entrega", "atualizado_em"])
        return self.proxima_entrega

    def pausar(self, ate=None):
        self.status = self.Status.PAUSADA
        self.pausada_ate = ate
        self.save(update_fields=["status", "pausada_ate", "atualizado_em"])

    def retomar(self):
        self.status = self.Status.ATIVA
        self.pausada_ate = None
        if self.proxima_entrega < timezone.localdate():
            self.proxima_entrega = timezone.localdate()
        self.save(
            update_fields=["status", "pausada_ate", "proxima_entrega", "atualizado_em"]
        )

    def cancelar(self, motivo=""):
        self.status = self.Status.CANCELADA
        self.cancelada_em = timezone.now()
        self.motivo_cancelamento = motivo
        self.save(
            update_fields=[
                "status", "cancelada_em", "motivo_cancelamento", "atualizado_em"
            ]
        )


class CicloAssinatura(TimeStampedModel):
    """Uma entrega da assinatura: cobrança + pedido gerado."""

    class Status(models.TextChoices):
        AGENDADO = "agendado", "Agendado"
        COBRANDO = "cobrando", "Processando cobrança"
        PAGO = "pago", "Pago"
        FALHOU = "falhou", "Falha na cobrança"
        PULADO = "pulado", "Pulado pelo cliente"
        CANCELADO = "cancelado", "Cancelado"

    assinatura = models.ForeignKey(
        Assinatura, on_delete=models.CASCADE, related_name="ciclos"
    )
    numero_ciclo = models.PositiveIntegerField(default=1)
    data_prevista = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AGENDADO)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    pedido = models.OneToOneField(
        "orders.Pedido", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ciclo_assinatura",
    )
    tentativas = models.PositiveIntegerField(default=0)
    erro = models.CharField(max_length=250, blank=True)
    processado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-data_prevista"]
        unique_together = [("assinatura", "numero_ciclo")]
        verbose_name = "ciclo da assinatura"
        verbose_name_plural = "ciclos das assinaturas"

    def __str__(self):
        return f"Ciclo {self.numero_ciclo} · {self.assinatura.produto.nome}"
