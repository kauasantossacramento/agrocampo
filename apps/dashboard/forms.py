"""Formulários do painel do lojista.

O lojista nunca deve precisar do admin do Django — aquilo é ferramenta de
analista. Tudo que ele edita no dia a dia passa por aqui, com rótulos em
português e validação pensada para uso no celular.
"""
from django import forms

from apps.catalog.models import Categoria, Marca, Produto, ProdutoImagem
from apps.core.models import SiteConfig
from apps.payments.models import ProvedorPagamento

CLASSE = "campo"


class _EstilizadoMixin:
    """Aplica a classe de input do design system em todos os campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect,
                                   forms.CheckboxSelectMultiple)):
                continue
            classes = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{classes} {CLASSE}".strip()


# ══════════════════════════════════════════════════════ produto (wizard)
class ProdutoForm(_EstilizadoMixin, forms.ModelForm):
    """Cadastro/edição de produto em um passo só de dados.

    O SKU é opcional: se vier vazio, geramos um. Cobrar SKU de quem está
    cadastrando pelo celular, no balcão, só atrapalha.
    """

    class Meta:
        model = Produto
        fields = (
            "nome", "categoria", "marca", "linha", "sku",
            "resumo", "descricao",
            "preco", "preco_promocional", "promocao_ate",
            "estoque", "estoque_minimo", "unidade", "peso_kg",
            "permite_assinatura", "desconto_assinatura_proprio",
            "destaque", "lancamento", "publicado",
        )
        widgets = {
            "nome": forms.TextInput(attrs={
                "placeholder": "Ex.: Ração Golden Fórmula Adulto 15kg",
                "autocomplete": "off",
            }),
            "sku": forms.TextInput(attrs={"placeholder": "Deixe vazio para gerar automático"}),
            "resumo": forms.TextInput(attrs={"placeholder": "Uma frase que aparece no card"}),
            "descricao": forms.Textarea(attrs={"rows": 4, "placeholder": "Detalhes do produto"}),
            "preco": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "0,00"}),
            "preco_promocional": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "opcional"}),
            "promocao_ate": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "estoque": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "estoque_minimo": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "peso_kg": forms.NumberInput(attrs={"step": "0.001", "inputmode": "decimal"}),
            "desconto_assinatura_proprio": forms.NumberInput(attrs={
                "inputmode": "numeric", "placeholder": "vazio = usa o global",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        self.fields["categoria"].queryset = Categoria.objects.publicados().order_by("nome")
        self.fields["marca"].queryset = Marca.objects.publicados().order_by("nome")
        self.fields["categoria"].empty_label = "Escolha a categoria"
        self.fields["marca"].empty_label = "Sem marca"
        self.fields["promocao_ate"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip().upper()
        if sku:
            return sku
        # gera na sequência do maior AGC-xxxx existente
        ultimo = (
            Produto.objects.filter(sku__startswith="AGC-")
            .order_by("-sku")
            .values_list("sku", flat=True)
            .first()
        )
        proximo = 1
        if ultimo:
            try:
                proximo = int(ultimo.split("-")[1]) + 1
            except (IndexError, ValueError):
                proximo = Produto.objects.count() + 1
        while Produto.objects.filter(sku=f"AGC-{proximo:04d}").exists():
            proximo += 1
        return f"AGC-{proximo:04d}"

    def clean(self):
        dados = super().clean()
        preco = dados.get("preco")
        promo = dados.get("preco_promocional")
        if preco and promo and promo >= preco:
            self.add_error(
                "preco_promocional",
                "O preço promocional precisa ser menor que o preço normal.",
            )
        return dados


class ProdutoImagemForm(forms.ModelForm):
    class Meta:
        model = ProdutoImagem
        fields = ("imagem", "legenda", "ordem")


# ══════════════════════════════════════════════════════ configurações
class AparenciaForm(_EstilizadoMixin, forms.ModelForm):
    """Identidade visual e textos da capa."""

    class Meta:
        model = SiteConfig
        fields = (
            "nome_loja", "chamada", "descricao",
            "logo", "logo_claro", "logo_altura", "favicon", "imagem_capa",
            "topbar_icone", "topbar_mensagem", "topbar_link_texto", "topbar_link_url",
        )
        widgets = {
            "chamada": forms.TextInput(attrs={"placeholder": "Frase principal do banner"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "topbar_mensagem": forms.TextInput(attrs={"placeholder": "Vazio esconde a faixa"}),
            "topbar_icone": forms.TextInput(attrs={"placeholder": "🚚", "maxlength": 8}),
        }


class ContatoForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = (
            "telefone", "whatsapp", "email_contato", "horario_atendimento",
            "endereco", "cidade_uf", "cep", "cnpj",
            "instagram", "facebook", "youtube", "rodape_sobre",
        )
        widgets = {
            "whatsapp": forms.TextInput(attrs={"placeholder": "5575900000000 (com DDI)"}),
            "cep": forms.TextInput(attrs={"data-mask": "cep", "placeholder": "00000-000"}),
            "telefone": forms.TextInput(attrs={"data-mask": "telefone"}),
            "rodape_sobre": forms.Textarea(attrs={"rows": 3}),
        }


class RegrasForm(_EstilizadoMixin, forms.ModelForm):
    """Regras comerciais — números que a loja promete e cumpre."""

    class Meta:
        model = SiteConfig
        fields = (
            "ano_fundacao",
            "frete_valor", "frete_gratis_acima_de",
            "desconto_assinatura_padrao", "desconto_pix",
            "blog_ativo",
            "pwa_convite_ativo", "pwa_convite_segundos", "pwa_convite_texto",
        )
        widgets = {
            "frete_valor": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "frete_gratis_acima_de": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        }


class EntregaForm(_EstilizadoMixin, forms.ModelForm):
    """Horário e avisos gerais de entrega.

    O frete de cada cidade fica em Conteúdo → Entrega; aqui ficam só as
    regras que valem para a loja inteira.
    """

    class Meta:
        model = SiteConfig
        fields = ("entrega_a_partir_de", "aviso_entrega",
                  "whatsapp_flutuante", "whatsapp_mensagem")
        widgets = {
            "entrega_a_partir_de": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "aviso_entrega": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Ex.: pedidos feitos após as 12h saem no dia seguinte.",
            }),
            "whatsapp_mensagem": forms.TextInput(attrs={
                "placeholder": "Olá! Vim pelo site e gostaria de tirar uma dúvida.",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entrega_a_partir_de"].input_formats = ["%H:%M"]
        self.fields["entrega_a_partir_de"].help_text = (
            "Aparece no checkout. Cada cidade pode ter um horário próprio."
        )


class VitrinesForm(_EstilizadoMixin, forms.ModelForm):
    """Títulos das três vitrines da home, editáveis pelo lojista."""

    class Meta:
        model = SiteConfig
        fields = (
            "vitrine_ouro_ativa", "vitrine_ouro_titulo",
            "vitrine_prata_ativa", "vitrine_prata_titulo",
            "vitrine_bronze_ativa", "vitrine_bronze_titulo",
        )
        labels = {
            "vitrine_ouro_titulo": "Título da vitrine Ouro",
            "vitrine_prata_titulo": "Título da vitrine Prata",
            "vitrine_bronze_titulo": "Título da vitrine Bronze",
            "vitrine_ouro_ativa": "Mostrar a vitrine Ouro na home",
            "vitrine_prata_ativa": "Mostrar a vitrine Prata na home",
            "vitrine_bronze_ativa": "Mostrar a vitrine Bronze na home",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for linha in ("ouro", "prata", "bronze"):
            self.fields[f"vitrine_{linha}_titulo"].help_text = (
                "A vitrine só aparece se houver produto nesta linha."
            )


class FirebaseForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = (
            "firebase_api_key", "firebase_auth_domain", "firebase_project_id",
            "firebase_storage_bucket", "firebase_messaging_sender_id",
            "firebase_app_id", "firebase_vapid_key", "firebase_service_account",
        )
        widgets = {
            "firebase_service_account": forms.Textarea(attrs={
                "rows": 5, "placeholder": '{"type": "service_account", ...}',
            }),
        }


class ProvedorPagamentoForm(_EstilizadoMixin, forms.ModelForm):
    """Credenciais da Stone e regras de cobrança, editáveis no painel."""

    class Meta:
        model = ProvedorPagamento
        fields = (
            "nome", "driver", "ambiente", "ativo",
            "stone_client_id", "stone_client_secret", "stone_api_key",
            "stone_merchant_id", "stone_affiliation_code",
            "stone_webhook_secret", "stone_pix_chave",
            "stone_base_url_sandbox", "stone_base_url_producao",
            "aceita_cartao", "aceita_pix", "aceita_boleto",
            "parcelas_maximas", "parcelas_sem_juros", "valor_minimo_parcela",
            "captura_automatica", "soft_descriptor", "pix_expira_em_minutos",
            "timeout_segundos",
        )
        widgets = {
            "stone_client_secret": forms.PasswordInput(render_value=True),
            "stone_api_key": forms.PasswordInput(render_value=True),
            "stone_webhook_secret": forms.PasswordInput(render_value=True),
            "valor_minimo_parcela": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "soft_descriptor": forms.TextInput(attrs={"maxlength": 22}),
        }

    def clean(self):
        dados = super().clean()

        if not any([dados.get("aceita_cartao"), dados.get("aceita_pix"),
                    dados.get("aceita_boleto")]):
            raise forms.ValidationError(
                "Deixe pelo menos um método de pagamento ativo — sem nenhum, "
                "ninguém consegue fechar pedido."
            )

        maximas = dados.get("parcelas_maximas") or 0
        sem_juros = dados.get("parcelas_sem_juros") or 0
        if sem_juros > maximas:
            self.add_error(
                "parcelas_sem_juros",
                f"Não pode ser maior que o total de parcelas ({maximas}x).",
            )

        # Stone de verdade exige o mínimo para autenticar
        if dados.get("driver") == ProvedorPagamento.Driver.STONE:
            faltando = [
                rotulo
                for campo, rotulo in (("stone_api_key", "API Key"),
                                      ("stone_merchant_id", "Merchant ID"))
                if not dados.get(campo)
            ]
            if faltando:
                self.add_error(
                    None,
                    "Para usar o driver Stone é preciso preencher: "
                    + ", ".join(faltando)
                    + ". Enquanto faltar, a loja opera em modo simulado.",
                )
        return dados
