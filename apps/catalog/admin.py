from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Avaliacao,
    Categoria,
    Especie,
    ListaDesejos,
    Marca,
    MovimentoEstoque,
    Produto,
    ProdutoImagem,
)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "pai", "ordem", "exibir_no_menu", "destaque_home", "publicado")
    list_filter = ("publicado", "exibir_no_menu", "destaque_home", "pai")
    list_editable = ("ordem", "exibir_no_menu", "destaque_home", "publicado")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ("nome", "destaque", "ordem", "publicado")
    list_editable = ("destaque", "ordem", "publicado")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Especie)
class EspecieAdmin(admin.ModelAdmin):
    list_display = ("nome", "grupo", "destaque_home", "ordem", "publicado")
    list_filter = ("grupo", "publicado", "destaque_home")
    list_editable = ("destaque_home", "ordem", "publicado")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}


class ProdutoImagemInline(admin.TabularInline):
    model = ProdutoImagem
    extra = 1
    fields = ("imagem", "legenda", "ordem")


class MovimentoEstoqueInline(admin.TabularInline):
    model = MovimentoEstoque
    extra = 0
    can_delete = False
    readonly_fields = ("tipo", "quantidade", "motivo", "pedido_referencia", "criado_em")
    max_num = 0


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "sku", "categoria", "marca", "preco_exibicao",
        "estoque_exibicao", "permite_assinatura", "destaque", "publicado",
    )
    list_filter = (
        "publicado", "destaque", "lancamento", "permite_assinatura",
        "categoria", "marca",
    )
    list_editable = ("destaque", "publicado")
    search_fields = ("nome", "sku", "descricao")
    prepopulated_fields = {"slug": ("nome",)}
    filter_horizontal = ("especies",)
    inlines = [ProdutoImagemInline, MovimentoEstoqueInline]
    readonly_fields = ("vendas", "criado_em", "atualizado_em")
    fieldsets = (
        ("Identificação", {"fields": ("nome", "slug", "sku", "categoria", "marca", "especies")}),
        ("Conteúdo", {"fields": ("resumo", "descricao", "beneficios", "composicao")}),
        (
            "Preços",
            {
                "fields": (
                    "preco", "preco_promocional", "promocao_ate", "preco_custo",
                    ("permite_assinatura", "desconto_assinatura"),
                )
            },
        ),
        ("Logística", {"fields": ("unidade", "peso_kg", "estoque", "estoque_minimo")}),
        ("Vitrine", {"fields": ("destaque", "lancamento", "publicado", "vendas")}),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    @admin.display(description="preço")
    def preco_exibicao(self, obj):
        if obj.promocao_vigente:
            return format_html(
                '<s style="color:#999">R$ {}</s> <b style="color:#2F9E44">R$ {}</b>',
                obj.preco,
                obj.preco_promocional,
            )
        return f"R$ {obj.preco}"

    @admin.display(description="estoque")
    def estoque_exibicao(self, obj):
        cor = "#D62B20" if obj.estoque <= 0 else ("#E2A100" if obj.estoque_baixo else "#2F9E44")
        return format_html('<b style="color:{}">{}</b>', cor, obj.estoque)


@admin.register(MovimentoEstoque)
class MovimentoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("produto", "tipo", "quantidade", "motivo", "pedido_referencia", "criado_em")
    list_filter = ("tipo", "criado_em")
    search_fields = ("produto__nome", "produto__sku", "pedido_referencia")


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = ("produto", "autor", "nota", "aprovada", "criado_em")
    list_filter = ("aprovada", "nota")
    list_editable = ("aprovada",)
    search_fields = ("produto__nome", "comentario")


admin.site.register(ListaDesejos)
