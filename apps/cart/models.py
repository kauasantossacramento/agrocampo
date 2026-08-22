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
        return self.itens.select_related(
            "produto", "produto__categoria", "variacao"
        ).prefetch_related("produto__imagens")

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
    def base_para_frete(self) -> Decimal:
        return self.subtotal - self.desconto_assinatura - self.desconto_cupom

    def entrega(self, endereco=None) -> dict:
        """Frete, prazo e avisos para um endereço. Sem endereço, usa o padrão.

        O frete real depende da cidade — e a cidade só é conhecida depois que
        o cliente escolhe o endereço. Antes disso a loja mostra o valor da
        cidade sede, que é o caso mais comum, deixando claro no checkout.
        """
        from apps.shipping.models import Cidade, calcular_frete

        if self.vazio:
            return {"valor": Decimal("0"), "cidade": None, "localidade": None,
                    "atendida": True, "prazo": None, "avisos": []}

        if endereco is None and self.usuario_id:
            endereco = self.usuario.endereco_padrao

        if endereco is None:
            # ainda não sabemos para onde vai: estima pela cidade sede
            sede = Cidade.objects.filter(sede=True, ativo=True).first()
            if sede:
                return {
                    "valor": sede.calcular_frete(self.base_para_frete),
                    "cidade": sede, "localidade": None, "atendida": True,
                    "prazo": sede.proxima_entrega(), "estimado": True,
                    "avisos": ["Frete estimado para "
                               f"{sede.nome}. Confirme o endereço no checkout."],
                }

        return calcular_frete(endereco, self.base_para_frete)

    @property
    def frete(self) -> Decimal:
        from apps.core.models import SiteConfig

        if self.vazio:
            return Decimal("0")

        entrega = self.entrega()
        if entrega["cidade"]:
            return entrega["valor"]

        # nenhuma cidade cadastrada ainda: cai na regra global da loja
        config = SiteConfig.load()
        # limite 0 desliga o frete gratis; sem isso um carrinho de R$ 0,01
        # ja sairia com frete gratis
        if config.frete_gratis_acima_de and self.base_para_frete >= config.frete_gratis_acima_de:
            return Decimal("0")
        return config.frete_valor

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
    def adicionar(self, produto, quantidade=1, recorrente=False, frequencia_dias=None,
                  variacao=None):
        if variacao is None and produto.tem_variacoes:
            variacao = produto.variacao_padrao
        item, criado = self.itens.get_or_create(
            produto=produto,
            variacao=variacao,
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
    variacao = models.ForeignKey(
        "catalog.VariacaoProduto", null=True, blank=True,
        on_delete=models.CASCADE, related_name="itens_carrinho",
        help_text="A apresentação escolhida: 2kg, 5kg, 500g…",
    )
    quantidade = models.PositiveIntegerField(default=1)
    recorrente = models.BooleanField(default=False)
    frequencia_dias = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["criado_em"]
        # a mesma ração em 2kg e em 5kg são duas linhas diferentes
        unique_together = [
            ("carrinho", "produto", "variacao", "recorrente", "frequencia_dias")
        ]
        verbose_name = "item do carrinho"
        verbose_name_plural = "itens do carrinho"

    def __str__(self):
        return f"{self.quantidade}x {self.nome_exibicao}"

    @property
    def nome_exibicao(self) -> str:
        if self.variacao:
            return f"{self.produto.nome} · {self.variacao.rotulo}"
        return self.produto.nome

    @property
    def foto(self):
        """A foto da variação escolhida, quando ela tem uma própria."""
        return self.variacao.foto if self.variacao else self.produto.foto_principal

    @property
    def _origem(self):
        return self.variacao or self.produto

    @property
    def preco_cheio(self) -> Decimal:
        return self._origem.preco_atual

    @property
    def preco_unitario(self) -> Decimal:
        origem = self._origem
        return origem.preco_assinatura if self.recorrente else origem.preco_atual

    @property
    def estoque_disponivel(self) -> int:
        return self.variacao.estoque if self.variacao else self.produto.estoque

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
        return self.produto.publicado and self.estoque_disponivel >= self.quantidade
