"""Notificações in-app + canais externos (e-mail, WhatsApp)."""
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class NotificacaoQuerySet(models.QuerySet):
    def nao_lidas(self):
        return self.filter(lida_em__isnull=True)

    def do_usuario(self, usuario):
        return self.filter(destinatario=usuario)

    def para_operadores(self):
        return self.filter(publico=Notificacao.Publico.LOJISTA)


class Notificacao(TimeStampedModel):
    class Tipo(models.TextChoices):
        PAGAMENTO_CONFIRMADO = "pagamento_confirmado", "Pagamento confirmado"
        PAGAMENTO_RECUSADO = "pagamento_recusado", "Pagamento recusado"
        PEDIDO_NOVO = "pedido_novo", "Novo pedido recebido"
        PEDIDO_APROVADO = "pedido_aprovado", "Pedido aprovado"
        PEDIDO_RECUSADO = "pedido_recusado", "Pedido recusado"
        PEDIDO_ENVIADO = "pedido_enviado", "Pedido enviado"
        ESTORNO = "estorno", "Estorno processado"
        ASSINATURA_RENOVADA = "assinatura_renovada", "Assinatura renovada"
        ASSINATURA_FALHOU = "assinatura_falhou", "Falha na assinatura"
        ESTOQUE_BAIXO = "estoque_baixo", "Estoque baixo"
        GERAL = "geral", "Geral"

    class Nivel(models.TextChoices):
        SUCESSO = "sucesso", "Sucesso"
        INFO = "info", "Informação"
        ALERTA = "alerta", "Alerta"
        ERRO = "erro", "Erro"

    class Publico(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        LOJISTA = "lojista", "Lojista"

    destinatario = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.CASCADE,
        related_name="notificacoes",
        help_text="Vazio + público=lojista significa notificação para toda a equipe.",
    )
    publico = models.CharField(max_length=15, choices=Publico.choices, default=Publico.CLIENTE)
    tipo = models.CharField(max_length=30, choices=Tipo.choices, default=Tipo.GERAL)
    nivel = models.CharField(max_length=15, choices=Nivel.choices, default=Nivel.INFO)

    titulo = models.CharField(max_length=140)
    mensagem = models.CharField(max_length=300, blank=True)
    link = models.CharField(max_length=300, blank=True)

    pedido = models.ForeignKey(
        "orders.Pedido", null=True, blank=True, on_delete=models.CASCADE,
        related_name="notificacoes",
    )

    lida_em = models.DateTimeField(null=True, blank=True)
    enviada_por_email = models.BooleanField(default=False)
    enviada_por_whatsapp = models.BooleanField(default=False)

    objects = NotificacaoQuerySet.as_manager()

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        indexes = [models.Index(fields=["destinatario", "lida_em"])]

    def __str__(self):
        return self.titulo

    @property
    def lida(self):
        return self.lida_em is not None

    @property
    def icone(self):
        return {
            self.Nivel.SUCESSO: "check",
            self.Nivel.INFO: "info",
            self.Nivel.ALERTA: "alert",
            self.Nivel.ERRO: "x",
        }.get(self.nivel, "info")

    def marcar_lida(self):
        if not self.lida_em:
            self.lida_em = timezone.now()
            self.save(update_fields=["lida_em"])


class MensagemWhatsApp(TimeStampedModel):
    """Trilha de cada aviso enviado (ou tentado) pelo WhatsApp automático.

    Existe para o lojista enxergar o que saiu e o que falhou sem precisar
    abrir log de container.
    """

    class Status(models.TextChoices):
        ENVIADA = "enviada", "Enviada"
        FALHOU = "falhou", "Falhou"
        IGNORADA = "ignorada", "Ignorada"

    notificacao = models.ForeignKey(
        Notificacao, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="mensagens_whatsapp",
    )
    pedido = models.ForeignKey(
        "orders.Pedido", null=True, blank=True, on_delete=models.CASCADE,
        related_name="mensagens_whatsapp",
    )
    numero = models.CharField(max_length=20, help_text="Só dígitos, com DDI.")
    texto = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices)
    erro = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "mensagem de WhatsApp"
        verbose_name_plural = "mensagens de WhatsApp"

    def __str__(self):
        return f"{self.numero} - {self.get_status_display()}"
