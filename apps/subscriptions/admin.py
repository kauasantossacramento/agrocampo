from django.contrib import admin

from .models import Assinatura, CicloAssinatura


class CicloInline(admin.TabularInline):
    model = CicloAssinatura
    extra = 0
    readonly_fields = ("numero_ciclo", "data_prevista", "status", "valor", "pedido", "erro")


@admin.register(Assinatura)
class AssinaturaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "produto", "quantidade", "frequencia_dias", "status", "proxima_entrega")
    list_filter = ("status", "frequencia_dias")
    search_fields = ("usuario__email", "produto__nome")
    date_hierarchy = "proxima_entrega"
    inlines = [CicloInline]
    actions = ["processar_agora"]

    @admin.action(description="Processar ciclo agora")
    def processar_agora(self, request, queryset):
        from .services import processar_ciclo

        for assinatura in queryset:
            processar_ciclo(assinatura)
        self.message_user(request, f"{queryset.count()} assinatura(s) processada(s).")


@admin.register(CicloAssinatura)
class CicloAssinaturaAdmin(admin.ModelAdmin):
    list_display = ("assinatura", "numero_ciclo", "data_prevista", "status", "valor", "pedido")
    list_filter = ("status",)
