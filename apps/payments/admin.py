from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CartaoTokenizado,
    Estorno,
    EventoWebhook,
    Pagamento,
    ProvedorPagamento,
    TransacaoPagamento,
)


@admin.register(ProvedorPagamento)
class ProvedorPagamentoAdmin(admin.ModelAdmin):
    """Onde as credenciais da Stone são cadastradas, sem precisar de deploy."""

    list_display = ("nome", "driver", "ambiente", "situacao", "padrao", "ativo")
    list_filter = ("driver", "ambiente", "ativo")
    list_editable = ("padrao", "ativo")
    readonly_fields = ("access_token_expira_em", "criado_em", "atualizado_em")
    fieldsets = (
        ("Identificação", {"fields": ("nome", "driver", "ambiente", ("ativo", "padrao"))}),
        (
            "Credenciais Stone",
            {
                "description": (
                    "Preencha com os dados fornecidos pela Stone. Enquanto a "
                    "API Key e o Merchant ID estiverem vazios, a loja opera "
                    "com o driver simulado e o checkout continua funcionando."
                ),
                "fields": (
                    "stone_client_id",
                    "stone_client_secret",
                    "stone_api_key",
                    "stone_merchant_id",
                    "stone_affiliation_code",
                    "stone_webhook_secret",
                    "stone_pix_chave",
                    ("stone_base_url_sandbox", "stone_base_url_producao"),
                    "access_token_expira_em",
                ),
            },
        ),
        (
            "Métodos aceitos",
            {"fields": (("aceita_cartao", "aceita_pix", "aceita_boleto"),)},
        ),
        (
            "Parcelamento",
            {"fields": (("parcelas_maximas", "parcelas_sem_juros"), "valor_minimo_parcela")},
        ),
        (
            "Comportamento",
            {
                "fields": (
                    "captura_automatica",
                    "soft_descriptor",
                    "pix_expira_em_minutos",
                    "timeout_segundos",
                )
            },
        ),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    @admin.display(description="situação")
    def situacao(self, obj):
        if obj.driver == ProvedorPagamento.Driver.SIMULADO:
            return format_html('<b style="color:#E2A100">Simulado</b>')
        if obj.credenciais_completas:
            return format_html('<b style="color:#2F9E44">Credenciais OK</b>')
        return format_html('<b style="color:#D62B20">Credenciais pendentes</b>')


class TransacaoInline(admin.TabularInline):
    model = TransacaoPagamento
    extra = 0
    can_delete = False
    max_num = 0
    readonly_fields = (
        "operacao", "sucesso", "http_status", "endpoint", "duracao_ms",
        "requisicao", "resposta", "erro", "criado_em",
    )


class EstornoInline(admin.TabularInline):
    model = Estorno
    extra = 0
    readonly_fields = ("referencia_externa", "concluido_em")


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "pedido", "metodo", "status_colorido", "valor",
        "parcelas", "referencia_externa", "criado_em",
    )
    list_filter = ("status", "metodo", "provedor", "criado_em")
    search_fields = ("pedido__numero", "referencia_externa", "nsu", "tid")
    readonly_fields = (
        "referencia_externa", "codigo_autorizacao", "nsu", "tid",
        "pix_qrcode", "pix_e2e_id", "pago_em", "idempotency_key",
        "criado_em", "atualizado_em",
    )
    inlines = [TransacaoInline, EstornoInline]

    @admin.display(description="status")
    def status_colorido(self, obj):
        cores = {
            "pago": "#2F9E44",
            "autorizado": "#2F6FB0",
            "pendente": "#E2A100",
            "processando": "#E2A100",
            "recusado": "#D62B20",
            "cancelado": "#8a7c70",
            "estornado": "#A81F17",
            "estorno_parcial": "#A81F17",
        }
        return format_html(
            '<b style="color:{}">{}</b>', cores.get(obj.status, "#221812"),
            obj.get_status_display(),
        )


@admin.register(EventoWebhook)
class EventoWebhookAdmin(admin.ModelAdmin):
    list_display = (
        "tipo", "referencia_externa", "assinatura_valida", "processado", "criado_em"
    )
    list_filter = ("processado", "assinatura_valida", "tipo")
    search_fields = ("referencia_externa", "tipo")
    readonly_fields = [f.name for f in EventoWebhook._meta.fields]
    actions = ["reprocessar"]

    @admin.action(description="Reprocessar eventos selecionados")
    def reprocessar(self, request, queryset):
        from .services import processar_webhook

        for evento in queryset:
            processar_webhook(evento)
        self.message_user(request, f"{queryset.count()} evento(s) reprocessado(s).")


@admin.register(Estorno)
class EstornoAdmin(admin.ModelAdmin):
    list_display = ("pagamento", "valor", "motivo", "status", "criado_em")
    list_filter = ("status", "motivo")
    search_fields = ("pagamento__pedido__numero", "referencia_externa")


@admin.register(TransacaoPagamento)
class TransacaoPagamentoAdmin(admin.ModelAdmin):
    list_display = ("pagamento", "operacao", "sucesso", "http_status", "duracao_ms", "criado_em")
    list_filter = ("operacao", "sucesso")
    readonly_fields = [f.name for f in TransacaoPagamento._meta.fields]


@admin.register(CartaoTokenizado)
class CartaoTokenizadoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "bandeira", "ultimos_digitos", "padrao", "ativo")
    list_filter = ("bandeira", "ativo")
    search_fields = ("usuario__email",)
    readonly_fields = ("token",)
