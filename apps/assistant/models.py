"""Assistente virtual (Silvinha): registro das conversas.

Guardar o que os clientes perguntam vale mais do que parece — é a lista de
dúvidas reais da loja, de graça. O lojista vê as últimas no painel.
"""
from django.db import models

from apps.core.models import TimeStampedModel


class ConversaAssistente(TimeStampedModel):
    sessao = models.CharField(max_length=64, db_index=True)
    usuario = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="conversas_assistente",
    )
    produto = models.ForeignKey(
        "catalog.Produto", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="conversas_assistente",
        help_text="Página em que a pergunta foi feita, se era de produto.",
    )
    pergunta = models.TextField()
    resposta = models.TextField()
    modelo = models.CharField(max_length=60, blank=True)
    falhou = models.BooleanField(default=False)
    erro = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "conversa da assistente"
        verbose_name_plural = "conversas da assistente"

    def __str__(self):
        return self.pergunta[:60]
