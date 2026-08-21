from django.contrib import admin

from .models import Carrinho, ItemCarrinho


class ItemCarrinhoInline(admin.TabularInline):
    model = ItemCarrinho
    extra = 0


@admin.register(Carrinho)
class CarrinhoAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "chave_sessao", "quantidade_itens", "finalizado", "atualizado_em")
    list_filter = ("finalizado",)
    inlines = [ItemCarrinhoInline]
