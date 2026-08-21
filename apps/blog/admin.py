from django.contrib import admin

from .models import CategoriaPost, Post


@admin.register(CategoriaPost)
class CategoriaPostAdmin(admin.ModelAdmin):
    list_display = ("nome", "cor")
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "autor", "destaque", "publicado", "publicado_em")
    list_filter = ("publicado", "destaque", "categoria")
    list_editable = ("destaque", "publicado")
    search_fields = ("titulo", "conteudo")
    prepopulated_fields = {"slug": ("titulo",)}
    filter_horizontal = ("produtos_relacionados",)
    date_hierarchy = "publicado_em"
