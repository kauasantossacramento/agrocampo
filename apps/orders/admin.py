from django.contrib import admin
from django.utils.html import format_html

from .models import Cupom, EventoPedido, ItemPedido, Pedido


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = ("nome_produto", "sku", "preco_cheio", "baixado_do_estoque")


class EventoPedidoInline(admin.TabularInline):
    model = EventoPedido
    extra = 0
    can_delete = False
    max_num = 0
    readonly_fields = ("status_anterior", "status_novo", "titulo", "descricao", "autor", "criado_em")


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("numero", "nome_cliente", "status_colorido", "total", "criado_em")
    list_filter = ("status", "criado_em")
    search_fields = ("numero", "nome_cliente", "email_cliente")
    date_hierarchy = "criado_em"
    inlines = [ItemPedidoInline, EventoPedidoInline]
    readonly_fields = (
        "numero", "subtotal", "desconto_assinatura", "total",
        "pago_em", "decidido_em", "enviado_em", "entregue_em",
        "criado_em", "atualizado_em",
    )

    @admin.display(description="status")
    def status_colorido(self, obj):
        cores = {
            "aguardando_pagamento": "#E2A100",
            "pago": "#2F9E44",
            "aguardando_aprovacao": "#E2A100",
            "aprovado": "#2F9E44",
            "em_separacao": "#2F6FB0",
            "enviado": "#0E8074",
            "entregue": "#1F6B31",
            "recusado": "#D62B20",
            "cancelado": "#8a7c70",
            "estornado": "#A81F17",
        }
        return format_html(
            '<b style="color:{}">{}</b>', cores.get(obj.status, "#221812"),
            obj.get_status_display(),
        )


@admin.register(Cupom)
class CupomAdmin(admin.ModelAdmin):
    list_display = ("codigo", "tipo", "valor", "valor_minimo", "usos", "usos_maximos", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("codigo",)


@admin.register(EventoPedido)
class EventoPedidoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "titulo", "status_novo", "autor", "criado_em")
    list_filter = ("status_novo",)
    search_fields = ("pedido__numero",)
