from django.contrib import admin

from .models import Notificacao


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "destinatario", "publico", "tipo", "nivel", "lida_em", "criado_em")
    list_filter = ("publico", "tipo", "nivel")
    search_fields = ("titulo", "mensagem", "destinatario__email")
