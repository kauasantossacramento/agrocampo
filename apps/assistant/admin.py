from django.contrib import admin

from .models import ConversaAssistente


@admin.register(ConversaAssistente)
class ConversaAssistenteAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "pergunta", "produto", "usuario", "falhou")
    list_filter = ("falhou", "modelo")
    search_fields = ("pergunta", "resposta")
    readonly_fields = [f.name for f in ConversaAssistente._meta.fields]
