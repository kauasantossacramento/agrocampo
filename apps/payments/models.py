"""Gateway de pagamento próprio da AgroCampo, conectado à Stone.

O desenho separa três camadas:

1. `ProvedorPagamento` — guarda **no banco** as credenciais e o comportamento
   do adquirente (Stone). É a fonte de verdade em runtime; as variáveis de
   ambiente servem só para o bootstrap inicial.
2. `Pagamento` — a intenção de pagamento de um pedido, com o ciclo de vida
   próprio da loja (pendente, autorizado, pago, recusado, estornado).
3. `TransacaoPagamento` / `EventoWebhook` — o rastro bruto de tudo que foi
   trocado com a Stone, para auditoria e conciliação.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class ProvedorPagamento(TimeStampedModel):
    """Configuração do adquirente. Cadastrável pelo painel, sem deploy.

    Os campos `stone_*` são os espaços reservados para a integração com a
    Stone. Enquanto estiverem vazios (ou com `ambiente=sandbox`), o driver
    de simulação assume, permitindo desenvolver o fluxo completo antes de
    ter as chaves em mãos.
    """

    class Driver(models.TextChoices):
        STONE = "stone", "Stone (produção/sandbox oficial)"
        SIMULADO = "simulado", "Simulado (desenvolvimento)"

    class Ambiente(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        PRODUCAO = "producao", "Produção"

    nome = models.CharField(max_length=80, default="Stone")
    driver = models.CharField(max_length=20, choices=Driver.choices, default=Driver.SIMULADO)
    ambiente = models.CharField(
        max_length=20, choices=Ambiente.choices, default=Ambiente.SANDBOX
    )
    ativo = models.BooleanField(default=True)
    padrao = models.BooleanField(
        "provedor padrão", default=False, help_text="Usado no checkout da loja."
    )

    # ------------------------------------------------------------------
    # CREDENCIAIS STONE — preencher no painel (Pagamentos > Provedores)
    # ------------------------------------------------------------------
    stone_client_id = models.CharField(
        "Stone · Client ID", max_length=200, blank=True,
        help_text="Identificador da aplicação OAuth fornecido pela Stone.",
    )
    stone_client_secret = models.CharField(
        "Stone · Client Secret", max_length=300, blank=True,
        help_text="Segredo OAuth. Nunca exibido no storefront.",
    )
    stone_api_key = models.CharField(
        "Stone · API Key", max_length=300, blank=True,
        help_text="Chave de API usada no header Authorization das chamadas.",
    )
    stone_merchant_id = models.CharField(
        "Stone · Merchant ID", max_length=120, blank=True,
        help_text="Identificador do estabelecimento (EC) na Stone.",
    )
    stone_affiliation_code = models.CharField(
        "Stone · Código de afiliação", max_length=120, blank=True,
        help_text="Stone Code / código de afiliação do lojista.",
    )
    stone_webhook_secret = models.CharField(
        "Stone · Segredo do webhook", max_length=300, blank=True,
        help_text="Usado para validar a assinatura HMAC das notificações.",
    )
    stone_pix_chave = models.CharField(
        "Stone · Chave Pix", max_length=200, blank=True,
        help_text="Chave Pix do recebedor, usada na geração do QR Code.",
    )
    stone_base_url_sandbox = models.URLField(
        "Stone · URL base (sandbox)",
        default="https://sandbox-api.stone.com.br",
        blank=True,
    )
    stone_base_url_producao = models.URLField(
        "Stone · URL base (produção)", default="https://api.stone.com.br", blank=True
    )

    # cache do token OAuth — preenchido pelo driver, não editar à mão
    access_token = models.TextField(blank=True, editable=False)
    access_token_expira_em = models.DateTimeField(null=True, blank=True, editable=False)

    # ------------------------------------------------------------------
    # CAPACIDADES E COMPORTAMENTO
    # ------------------------------------------------------------------
    aceita_cartao = models.BooleanField("aceita cartão de crédito", default=True)
    aceita_pix = models.BooleanField(default=True)
    aceita_boleto = models.BooleanField(default=False)

    parcelas_maximas = models.PositiveIntegerField(default=12)
    parcelas_sem_juros = models.PositiveIntegerField(default=3)
    valor_minimo_parcela = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("30.00")
    )

    captura_automatica = models.BooleanField(
        default=True,
        help_text="Se desmarcado, a loja apenas autoriza e captura após a aprovação do lojista.",
    )
    soft_descriptor = models.CharField(
        max_length=22, default="AGROCAMPO",
        help_text="Texto exibido na fatura do cartão (máx. 22 caracteres).",
    )
    pix_expira_em_minutos = models.PositiveIntegerField(default=30)
    timeout_segundos = models.PositiveIntegerField(default=30)

    class Meta:
        ordering = ["-padrao", "nome"]
        verbose_name = "provedor de pagamento"
        verbose_name_plural = "provedores de pagamento"

    def __str__(self):
        return f"{self.nome} ({self.get_ambiente_display()})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.padrao:
            ProvedorPagamento.objects.exclude(pk=self.pk).update(padrao=False)

    @classmethod
    def ativo_padrao(cls):
        """Provedor usado pelo checkout. Cria um simulado se não houver nenhum."""
        provedor = cls.objects.filter(ativo=True, padrao=True).first()
        if provedor:
            return provedor
        provedor = cls.objects.filter(ativo=True).first()
        if provedor:
            return provedor
        return cls.objects.create(
            nome="Stone", driver=cls.Driver.SIMULADO, padrao=True, ativo=True
        )

    @property
    def base_url(self):
        return (
            self.stone_base_url_producao
            if self.ambiente == self.Ambiente.PRODUCAO
            else self.stone_base_url_sandbox
        )

    @property
    def credenciais_completas(self):
        """True quando há o mínimo para falar com a Stone de verdade."""
        return bool(self.stone_api_key and self.stone_merchant_id)

    @property
    def token_valido(self):
        return bool(
            self.access_token
            and self.access_token_expira_em
            and self.access_token_expira_em > timezone.now()
        )

    def metodos_disponiveis(self):
        metodos = []
        if self.aceita_cartao:
            metodos.append(Pagamento.Metodo.CARTAO)
        if self.aceita_pix:
            metodos.append(Pagamento.Metodo.PIX)
        if self.aceita_boleto:
            metodos.append(Pagamento.Metodo.BOLETO)
        return metodos

    def parcelas_disponiveis(self, total: Decimal):
        """Opções de parcelamento válidas para um total, respeitando o mínimo."""
        opcoes = []
        for n in range(1, self.parcelas_maximas + 1):
            valor = (total / n).quantize(Decimal("0.01"))
            if n > 1 and valor < self.valor_minimo_parcela:
                break
            opcoes.append(
                {"parcelas": n, "valor": valor, "sem_juros": n <= self.parcelas_sem_juros}
            )
        return opcoes


class Pagamento(TimeStampedModel):
    """Intenção de pagamento de um pedido."""

    class Metodo(models.TextChoices):
        CARTAO = "cartao", "Cartão de crédito"
        PIX = "pix", "Pix"
        BOLETO = "boleto", "Boleto"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Aguardando pagamento"
        PROCESSANDO = "processando", "Processando"
        AUTORIZADO = "autorizado", "Autorizado (não capturado)"
        PAGO = "pago", "Pago"
        RECUSADO = "recusado", "Recusado"
        CANCELADO = "cancelado", "Cancelado"
        ESTORNADO = "estornado", "Estornado"
        ESTORNO_PARCIAL = "estorno_parcial", "Estornado parcialmente"

    STATUS_FINAIS = {Status.PAGO, Status.RECUSADO, Status.CANCELADO, Status.ESTORNADO}

    pedido = models.ForeignKey(
        "orders.Pedido", on_delete=models.CASCADE, related_name="pagamentos"
    )
    provedor = models.ForeignKey(
        ProvedorPagamento, on_delete=models.PROTECT, related_name="pagamentos"
    )

    metodo = models.CharField(max_length=20, choices=Metodo.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)

    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valor_capturado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_estornado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    parcelas = models.PositiveIntegerField(default=1)

    # ------------------------- identificadores devolvidos pela Stone -----
    referencia_externa = models.CharField(
        "ID na Stone", max_length=120, blank=True, db_index=True,
        help_text="charge_id / transaction_id retornado pelo adquirente.",
    )
    codigo_autorizacao = models.CharField(max_length=60, blank=True)
    nsu = models.CharField("NSU", max_length=60, blank=True)
    tid = models.CharField("TID", max_length=60, blank=True)
    bandeira = models.CharField(max_length=30, blank=True)
    ultimos_digitos = models.CharField(max_length=4, blank=True)

    # --------------------------------------------------------------- Pix
    pix_qrcode = models.TextField(blank=True, help_text="Payload copia-e-cola (BR Code).")
    pix_qrcode_imagem = models.URLField(blank=True, max_length=500)
    pix_expira_em = models.DateTimeField(null=True, blank=True)
    pix_e2e_id = models.CharField("Pix EndToEndId", max_length=60, blank=True)

    # ------------------------------------------------------------ boleto
    boleto_url = models.URLField(blank=True, max_length=500)
    boleto_linha_digitavel = models.CharField(max_length=60, blank=True)
    boleto_vencimento = models.DateField(null=True, blank=True)

    # --------------------------------------------------------- resultado
    mensagem = models.CharField(max_length=250, blank=True)
    codigo_retorno = models.CharField(max_length=40, blank=True)
    pago_em = models.DateTimeField(null=True, blank=True)

    idempotency_key = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        indexes = [models.Index(fields=["status", "metodo"])]

    def __str__(self):
        return f"{self.get_metodo_display()} · {self.valor} · {self.get_status_display()}"

    @property
    def liquidado(self):
        return self.status == self.Status.PAGO

    @property
    def valor_estornavel(self) -> Decimal:
        return (self.valor_capturado or self.valor) - self.valor_estornado

    @property
    def pix_expirado(self):
        return bool(self.pix_expira_em and self.pix_expira_em < timezone.now())

    def marcar_pago(self, referencia="", mensagem=""):
        self.status = self.Status.PAGO
        self.valor_capturado = self.valor
        self.pago_em = timezone.now()
        if referencia:
            self.referencia_externa = referencia
        if mensagem:
            self.mensagem = mensagem
        self.save(
            update_fields=[
                "status", "valor_capturado", "pago_em",
                "referencia_externa", "mensagem", "atualizado_em",
            ]
        )

    def marcar_recusado(self, mensagem="", codigo=""):
        self.status = self.Status.RECUSADO
        self.mensagem = mensagem or "Pagamento recusado pelo emissor."
        self.codigo_retorno = codigo
        self.save(
            update_fields=["status", "mensagem", "codigo_retorno", "atualizado_em"]
        )

    def registrar_estorno(self, valor: Decimal):
        self.valor_estornado = (self.valor_estornado or Decimal("0")) + valor
        self.status = (
            self.Status.ESTORNADO
            if self.valor_estornado >= (self.valor_capturado or self.valor)
            else self.Status.ESTORNO_PARCIAL
        )
        self.save(update_fields=["valor_estornado", "status", "atualizado_em"])


class TransacaoPagamento(TimeStampedModel):
    """Registro bruto de cada chamada ao adquirente — trilha de auditoria."""

    class Operacao(models.TextChoices):
        AUTORIZACAO = "autorizacao", "Autorização"
        CAPTURA = "captura", "Captura"
        CONSULTA = "consulta", "Consulta"
        ESTORNO = "estorno", "Estorno"
        CANCELAMENTO = "cancelamento", "Cancelamento"
        TOKENIZACAO = "tokenizacao", "Tokenização de cartão"
        RECORRENCIA = "recorrencia", "Cobrança recorrente"

    pagamento = models.ForeignKey(
        Pagamento, on_delete=models.CASCADE, related_name="transacoes"
    )
    operacao = models.CharField(max_length=20, choices=Operacao.choices)
    sucesso = models.BooleanField(default=False)
    http_status = models.PositiveIntegerField(null=True, blank=True)
    endpoint = models.CharField(max_length=250, blank=True)
    requisicao = models.JSONField(default=dict, blank=True)
    resposta = models.JSONField(default=dict, blank=True)
    duracao_ms = models.PositiveIntegerField(null=True, blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "transação com o adquirente"
        verbose_name_plural = "transações com o adquirente"

    def __str__(self):
        return f"{self.get_operacao_display()} · {'ok' if self.sucesso else 'falha'}"


class EventoWebhook(TimeStampedModel):
    """Notificação recebida da Stone. Guardada antes de ser processada."""

    provedor = models.ForeignKey(
        ProvedorPagamento, on_delete=models.CASCADE, related_name="webhooks", null=True, blank=True
    )
    tipo = models.CharField(max_length=80, blank=True)
    referencia_externa = models.CharField(max_length=120, blank=True, db_index=True)
    assinatura = models.CharField(max_length=300, blank=True)
    assinatura_valida = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)
    processado = models.BooleanField(default=False)
    processado_em = models.DateTimeField(null=True, blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "evento de webhook"
        verbose_name_plural = "eventos de webhook"

    def __str__(self):
        return f"{self.tipo or 'evento'} · {self.referencia_externa}"


class Estorno(TimeStampedModel):
    class Status(models.TextChoices):
        SOLICITADO = "solicitado", "Solicitado"
        PROCESSANDO = "processando", "Processando"
        CONCLUIDO = "concluido", "Concluído"
        FALHOU = "falhou", "Falhou"

    class Motivo(models.TextChoices):
        SEM_ESTOQUE = "sem_estoque", "Produto sem estoque"
        PEDIDO_RECUSADO = "pedido_recusado", "Pedido recusado pelo lojista"
        DESISTENCIA = "desistencia", "Desistência do cliente"
        DUPLICIDADE = "duplicidade", "Cobrança em duplicidade"
        OUTRO = "outro", "Outro"

    pagamento = models.ForeignKey(Pagamento, on_delete=models.CASCADE, related_name="estornos")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=30, choices=Motivo.choices, default=Motivo.OUTRO)
    observacao = models.CharField(max_length=250, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SOLICITADO)
    referencia_externa = models.CharField(max_length=120, blank=True)
    solicitado_por = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="estornos_solicitados",
    )
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "estorno"
        verbose_name_plural = "estornos"

    def __str__(self):
        return f"Estorno de {self.valor} · {self.get_status_display()}"


class CartaoTokenizado(TimeStampedModel):
    """Cartão salvo na Stone (apenas o token trafega/persiste aqui).

    Nenhum dado sensível (PAN completo, CVV) é gravado no banco da loja —
    a tokenização acontece no adquirente e guardamos só a referência.
    """

    usuario = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="cartoes"
    )
    provedor = models.ForeignKey(
        ProvedorPagamento, on_delete=models.CASCADE, related_name="cartoes"
    )
    token = models.CharField(max_length=250, help_text="Token/card_id devolvido pela Stone.")
    bandeira = models.CharField(max_length=30, blank=True)
    ultimos_digitos = models.CharField(max_length=4)
    nome_impresso = models.CharField(max_length=120, blank=True)
    validade_mes = models.PositiveSmallIntegerField()
    validade_ano = models.PositiveSmallIntegerField()
    padrao = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-padrao", "-criado_em"]
        verbose_name = "cartão tokenizado"
        verbose_name_plural = "cartões tokenizados"

    def __str__(self):
        return f"{self.bandeira} •••• {self.ultimos_digitos}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.padrao:
            CartaoTokenizado.objects.filter(usuario=self.usuario).exclude(pk=self.pk).update(
                padrao=False
            )
