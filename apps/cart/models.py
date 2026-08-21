"""Carrinho persistente: funciona anônimo (por sessão) e migra no login."""
from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class Carrinho(TimeStampedModel):
    usuario = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.CASCADE,
        related_name="carrinhos",
    )
    chave_sessao = models.CharField(max_length=60, blank=True, db_index=True)
    cupom = models.ForeignKey(
        "orders.Cupom", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="carrinhos",
    )
    finalizado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-atualizado_em"]
        verbose_name = "carrinho"
        verbose_name_plural = "carrinhos"

    def __str__(self):
        dono = self.usuario or f"sessão {self.chave_sessao[:8]}"
        return f"Carrinho de {dono} ({self.quantidade_itens} itens)"

    # ------------------------------------------------------------ totais
    @property
    def linhas(self):
        return self.itens.select_related("produto", "produto__categoria").prefetch_related(
            "produto__imagens"
        )

    @property
    def vazio(self):
        return not self.itens.exists()

    @property
    def quantidade_itens(self):
        return sum(i.quantidade for i in self.itens.all())

    @property
    def subtotal(self) -> Decimal:
        """Soma pelos preços de tabela, antes do desconto de assinatura."""
        return sum((i.preco_cheio * i.quantidade for i in self.linhas), Decimal("0"))

    @property
    def desconto_assinatura(self) -> Decimal:
        return sum((i.economia for i in self.linhas), Decimal("0"))

    @property
    def desconto_cupom(self) -> Decimal:
        base = self.subtotal - self.desconto_assinatura
        return self.cupom.calcular(base) if self.cupom else Decimal("0")

    @property
    def frete(self) -> Decimal:
        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        base = self.subtotal - self.desconto_assinatura - self.desconto_cupom
        if base >= config.frete_gratis_acima_de or self.vazio:
            return Decimal("0")
        return Decimal("24.90")

    @property
    def frete_gratis(self) -> bool:
        return self.frete == 0 and not self.vazio

    @property
    def falta_para_frete_gratis(self) -> Decimal:
        from apps.core.models import SiteConfig

        alvo = SiteConfig.load().frete_gratis_acima_de
        base = self.subtotal - self.desconto_assinatura - self.desconto_cupom
        return max(Decimal("0"), alvo - base)

    @property
    def total(self) -> Decimal:
        return (
            self.subtotal - self.desconto_assinatura - self.desconto_cupom + self.frete
        )

    @property
    def tem_recorrencia(self):
        return self.itens.filter(recorrente=True).exists()

    # ---------------------------------------------------------- operacoes
    def adicionar(self, produto, quantidade=1, recorrente=False, frequencia_dias=None):
        item, criado = self.itens.get_or_create(
            produto=produto,
            recorrente=recorrente,
            frequencia_dias=frequencia_dias if recorrente else None,
            defaults={"quantidade": quantidade},
        )
        if not criado:
            item.quantidade = models.F("quantidade") + quantidade
            item.save(update_fields=["quantidade"])
            item.refresh_from_db()
        return item

    def mesclar(self, outro):
        """Traz os itens de um carrinho anônimo para o do usuário logado."""
        for item in outro.itens.all():
            self.adicionar(
                item.produto, item.quantidade, item.recorrente, item.frequencia_dias
            )
        outro.delete()
        return self

    def limpar(self):
        self.itens.all().delete()
        self.cupom = None
        self.save(update_fields=["cupom", "atualizado_em"])


class ItemCarrinho(TimeStampedModel):
    FREQUENCIAS = [(30, "A cada 30 dias"), (60, "A cada 60 dias"), (90, "A cada 90 dias")]

    carrinho = models.ForeignKey(Carrinho, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(
        "catalog.Produto", on_delete=models.CASCADE, related_name="itens_carrinho"
    )
    quantidade = models.PositiveIntegerField(default=1)
    recorrente = models.BooleanField(default=False)
    frequencia_dias = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["criado_em"]
        unique_together = [("carrinho", "produto", "recorrente", "frequencia_dias")]
        verbose_name = "item do carrinho"
        verbose_name_plural = "itens do carrinho"

    def __str__(self):
        return f"{self.quantidade}x {self.produto.nome}"

    @property
    def preco_cheio(self) -> Decimal:
        return self.produto.preco_atual

    @property
    def preco_unitario(self) -> Decimal:
        return (
            self.produto.preco_assinatura if self.recorrente else self.produto.preco_atual
        )

    @property
    def total(self) -> Decimal:
        return self.preco_unitario * self.quantidade

    @property
    def economia(self) -> Decimal:
        return (self.preco_cheio - self.preco_unitario) * self.quantidade

    @property
    def rotulo_frequencia(self):
        if not self.recorrente:
            return "Compra única"
        return f"Recorrente · a cada {self.frequencia_dias} dias"

    @property
    def disponivel(self):
        return self.produto.publicado and self.produto.estoque >= self.quantidade
