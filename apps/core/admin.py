from django.contrib import admin
from django.utils.html import format_html

from .models import AssinanteNewsletter, Banner, Diferencial, Pagina, SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """Tudo que o lojista pode trocar sem mexer em código."""

    fieldsets = (
        (
            "Identidade",
            {"fields": ("nome_loja", "chamada", "descricao")},
        ),
        (
            "Imagens",
            {
                "description": (
                    "A <b>imagem de capa</b> é a figura recortada que aparece no "
                    "banner da home. Cada banner pode ter a sua; esta vale como padrão."
                ),
                "fields": ("logo", "logo_claro", "favicon", "imagem_capa", "previa_capa"),
            },
        ),
        (
            "Faixa do topo",
            {
                "description": "Barra escura acima do cabeçalho. Mensagem vazia esconde a barra.",
                "fields": (
                    "topbar_icone",
                    "topbar_mensagem",
                    ("topbar_link_texto", "topbar_link_url"),
                ),
            },
        ),
        (
            "Contato",
            {
                "fields": (
                    "telefone",
                    "whatsapp",
                    "email_contato",
                    "horario_atendimento",
                    "endereco",
                    ("cidade_uf", "cep"),
                    "cnpj",
                )
            },
        ),
        ("Redes sociais", {"fields": ("instagram", "facebook", "youtube")}),
        (
            "Aplicativo (PWA)",
            {
                "description": "Convite para instalar o app, exibido a quem ainda não instalou.",
                "fields": ("pwa_convite_ativo", "pwa_convite_segundos", "pwa_convite_texto"),
            },
        ),
        (
            "Firebase — notificações push",
            {
                "classes": ("collapse",),
                "description": (
                    "Console do Firebase › Configurações do projeto. Enquanto estiver "
                    "vazio o push fica desligado e a loja segue com as notificações "
                    "internas. O <b>JSON da conta de serviço</b> é segredo do servidor "
                    "e nunca vai para o navegador."
                ),
                "fields": (
                    "firebase_api_key",
                    "firebase_auth_domain",
                    "firebase_project_id",
                    "firebase_storage_bucket",
                    "firebase_messaging_sender_id",
                    "firebase_app_id",
                    "firebase_vapid_key",
                    "firebase_service_account",
                ),
            },
        ),
        ("Rodapé", {"fields": ("rodape_sobre",)}),
        (
            "Regras da loja",
            {
                "description": (
                    "O <b>desconto da assinatura</b> vale para o site inteiro. "
                    "Produtos com percentual próprio (no cadastro do produto) "
                    "ignoram este valor."
                ),
                "fields": (
                    "ano_fundacao",
                    "blog_ativo",
                    "frete_gratis_acima_de",
                    "desconto_assinatura_padrao",
                    "desconto_pix",
                    "parcelas_maximas",
                )
            },
        ),
    )
    readonly_fields = ("previa_capa",)

    @admin.display(description="prévia da capa")
    def previa_capa(self, obj):
        if not obj.imagem_capa:
            return "Nenhuma imagem enviada — a loja usa a figura padrão."
        return format_html(
            '<div style="background:#D62B20;border-radius:12px;padding:12px;'
            'display:inline-block"><img src="{}" style="max-height:220px;'
            'width:auto;display:block"></div>',
            obj.imagem_capa.url,
        )

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("titulo", "posicao", "tem_imagem", "ordem", "publicado")
    list_filter = ("posicao", "publicado")
    list_editable = ("ordem", "publicado")
    readonly_fields = ("previa",)
    fieldsets = (
        ("Conteúdo", {"fields": ("selo", "titulo", "subtitulo")}),
        (
            "Imagem de capa deste banner",
            {
                "description": (
                    "PNG com fundo transparente funciona melhor. Se ficar vazio, "
                    "a loja usa a imagem de capa da configuração geral."
                ),
                "fields": ("imagem", "previa"),
            },
        ),
        ("Ação", {"fields": ("texto_botao", "link")}),
        ("Exibição", {"fields": ("posicao", "cor_fundo", "ordem", "publicado")}),
    )

    @admin.display(description="imagem", boolean=True)
    def tem_imagem(self, obj):
        return bool(obj.imagem)

    @admin.display(description="prévia")
    def previa(self, obj):
        if not obj.imagem:
            return "Sem imagem própria — usará a capa padrão da loja."
        return format_html(
            '<div style="background:{};border-radius:12px;padding:12px;'
            'display:inline-block"><img src="{}" style="max-height:220px;'
            'width:auto;display:block"></div>',
            obj.cor_fundo or "#D62B20",
            obj.imagem.url,
        )


@admin.register(Diferencial)
class DiferencialAdmin(admin.ModelAdmin):
    list_display = ("titulo", "descricao", "icone", "ordem", "publicado")
    list_editable = ("ordem", "publicado")


@admin.register(Pagina)
class PaginaAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordem_rodape", "publicado")
    list_editable = ("ordem_rodape", "publicado")
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(AssinanteNewsletter)
class AssinanteNewsletterAdmin(admin.ModelAdmin):
    list_display = ("email", "nome", "ativo", "criado_em")
    search_fields = ("email",)
