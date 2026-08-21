from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Endereco, User


class EnderecoInline(admin.TabularInline):
    model = Endereco
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "papel", "is_staff", "date_joined")
    list_filter = ("papel", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "first_name", "last_name", "cpf")
    ordering = ("-date_joined",)
    inlines = [EnderecoInline]
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "cpf", "telefone", "data_nascimento")}),
        ("Loja", {"fields": ("papel", "aceita_marketing")}),
        ("Permissoes", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "username", "password1", "password2")}),
    )


@admin.register(Endereco)
class EnderecoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "apelido", "cidade", "uf", "zona_rural", "padrao")
    list_filter = ("uf", "zona_rural", "padrao")
    search_fields = ("usuario__email", "cep", "cidade")
