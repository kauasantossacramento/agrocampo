"""Formulários do painel do lojista.

O lojista nunca deve precisar do admin do Django — aquilo é ferramenta de
analista. Tudo que ele edita no dia a dia passa por aqui, com rótulos em
português e validação pensada para uso no celular.
"""
from django import forms

from apps.catalog.models import (Categoria, Especie, LinhaProduto, Marca, Produto,
                                 ProdutoImagem)
from apps.core.models import SiteConfig
from apps.payments.models import ProvedorPagamento

CLASSE = "campo"


def campo_livre(rotulo, tipo, ajuda, placeholder, obrigatorio=False, **extra):
    """Campo de texto com sugestões do que já existe e criação do que faltar.

    Usado no cadastro de produto para marca, categoria, linha e animal: o
    lojista digita, as opções já cadastradas aparecem como sugestão e o nome
    novo passa a existir — pelo Enter (JS) ou na hora de salvar.
    """
    return forms.CharField(
        label=rotulo, max_length=250, required=obrigatorio,
        widget=forms.TextInput(attrs={
            "list": f"lista-{tipo}", "autocomplete": "off",
            "placeholder": placeholder, "data-livre": tipo, **extra,
        }),
        help_text=ajuda,
    )


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
            "nome", "sku",
            "resumo", "descricao",
            "preco", "preco_promocional", "promocao_ate",
            "sem_controle_estoque", "estoque", "estoque_minimo", "unidade", "peso_kg", "proteina",
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
            "descricao": forms.Textarea(attrs={
                "rows": 10, "data-autogrow": "", "placeholder":
                "Detalhes do produto — pode escrever à vontade; a caixa cresce "
                "conforme você digita.",
            }),
            "preco": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "0,00"}),
            "preco_promocional": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "opcional"}),
            "promocao_ate": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "estoque": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "estoque_minimo": forms.NumberInput(attrs={"inputmode": "numeric"}),
            "peso_kg": forms.NumberInput(attrs={"step": "0.001", "inputmode": "decimal"}),
            "proteina": forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "ex.: 26"}),
            "desconto_assinatura_proprio": forms.NumberInput(attrs={
                "inputmode": "numeric", "placeholder": "vazio = usa o global",
            }),
        }

    # Nada no cadastro é lista fechada: marca, categoria, linha e animal são
    # digitados, com sugestão do que já existe e criação do que faltar.
    marca_nome = campo_livre(
        "Marca", "marcas",
        "Escolha uma da lista ou escreva o nome de uma marca nova.",
        "Digite e pressione Enter para criar",
    )
    categoria_nome = campo_livre(
        "Categoria", "categorias",
        "Escolha uma da lista ou escreva o nome de uma categoria nova.",
        "Digite e pressione Enter para criar",
        obrigatorio=True,
    )
    linha_nome = campo_livre(
        "Linha", "linhas",
        "Define o selo do produto e em qual vitrine ele aparece. "
        "Pode criar uma linha nova digitando o nome.",
        "Ex.: Super Premium — digite e pressione Enter",
    )
    especies_nomes = campo_livre(
        "Indicado para (animais)", "especies",
        "Separe por vírgula. Animal que ainda não existe é criado na hora.",
        "Cão, Gato, Calopsita…",
        **{"data-multiplo": "1"},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        self.fields["promocao_ate"].input_formats = ["%Y-%m-%dT%H:%M"]
        # os campos de relação saem: quem manda são os de texto acima
        for campo in ("marca", "categoria", "linha", "especies"):
            self.fields.pop(campo, None)
        self.fields["unidade"].widget = forms.TextInput(attrs={
            "class": CLASSE, "list": "lista-unidades", "autocomplete": "off",
            "placeholder": "un, kg, g, L…",
        })
        self.fields["unidade"].required = False
        if self.is_bound or not self.instance:
            return
        if self.instance.marca_id:
            self.fields["marca_nome"].initial = self.instance.marca.nome
        if self.instance.categoria_id:
            self.fields["categoria_nome"].initial = self.instance.categoria.nome
        if self.instance.linha_id:
            self.fields["linha_nome"].initial = self.instance.linha.nome
        if self.instance.pk:
            self.fields["especies_nomes"].initial = ", ".join(
                self.instance.especies.values_list("nome", flat=True)
            )

    @staticmethod
    def _obter_ou_criar(modelo, nome):
        """Nome igual (ignorando maiúsculas) reaproveita; o resto vira cadastro novo."""
        nome = " ".join((nome or "").split())[:180]
        if not nome:
            return None
        return (modelo.objects.filter(nome__iexact=nome).first()
                or modelo.objects.create(nome=nome))

    def clean_marca_nome(self):
        return self._obter_ou_criar(Marca, self.cleaned_data.get("marca_nome"))

    def clean_categoria_nome(self):
        categoria = self._obter_ou_criar(Categoria, self.cleaned_data.get("categoria_nome"))
        if not categoria:
            raise forms.ValidationError("Escreva a categoria do produto.")
        return categoria

    def clean_linha_nome(self):
        return self._obter_ou_criar(LinhaProduto, self.cleaned_data.get("linha_nome"))

    def clean_especies_nomes(self):
        nomes = (self.cleaned_data.get("especies_nomes") or "").split(",")
        achados = (self._obter_ou_criar(Especie, nome) for nome in nomes)
        return [especie for especie in achados if especie]

    def clean_unidade(self):
        return (self.cleaned_data.get("unidade") or "un").strip().lower()[:5] or "un"

    def save(self, commit=True):
        produto = super().save(commit=False)
        produto.marca = self.cleaned_data.get("marca_nome")
        produto.categoria = self.cleaned_data.get("categoria_nome")
        produto.linha = self.cleaned_data.get("linha_nome")
        if commit:
            produto.save()
            self.save_m2m()
            produto.especies.set(self.cleaned_data.get("especies_nomes") or [])
        return produto

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
    """Identidade visual e textos da capa.

    Cada campo de imagem tem uma caixa "Remover" (`<campo>-clear`), porque
    trocar exigia sempre subir outra no lugar — não havia como voltar ao
    padrão do tema.
    """

    IMAGENS = ("logo", "logo_claro", "favicon", "imagem_capa")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # o estilo da home é opcional no envio: faltando, fica o que está
        self.fields["layout_home"].required = False
        if not self.is_bound:
            return
        # Marcar "Remover" e escolher outra imagem no mesmo envio: o Django
        # trata como contradição e mantém a antiga. Enviar arquivo é intenção
        # clara de substituir, então a caixa perde a vez.
        for campo in self.IMAGENS:
            if self.files.get(campo) and self.data.get(f"{campo}-clear"):
                self.data = self.data.copy()
                self.data.pop(f"{campo}-clear", None)

    class Meta:
        model = SiteConfig
        fields = (
            "nome_loja", "chamada", "descricao", "layout_home",
            "capa_slides_ativa", "capa_apresentacao_ativa",
            "logo", "logo_claro", "logo_altura", "favicon", "imagem_capa",
            "topbar_icone", "topbar_mensagem", "topbar_link_texto", "topbar_link_url",
        )
        widgets = {
            "chamada": forms.TextInput(attrs={"placeholder": "Frase principal do banner"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "topbar_mensagem": forms.TextInput(attrs={"placeholder": "Vazio esconde a faixa"}),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/*", "hidden": True}),
            "logo_claro": forms.ClearableFileInput(attrs={"accept": "image/*", "hidden": True}),
            "favicon": forms.ClearableFileInput(attrs={"accept": "image/*", "hidden": True}),
            "imagem_capa": forms.ClearableFileInput(attrs={"accept": "image/*", "hidden": True}),
            "topbar_icone": forms.TextInput(attrs={"placeholder": "🚚", "maxlength": 8}),
        }

    def clean_layout_home(self):
        return self.cleaned_data.get("layout_home") or self.instance.layout_home

    def save(self, commit=True):
        config = super().save(commit=False)
        for campo in self.IMAGENS:
            # o widget nativo do Django usa "<campo>-clear"; o template
            # desenha a caixa à mão para caber no cartão de pré-visualização
            if self.data.get(f"{campo}-clear") and not self.files.get(campo):
                getattr(config, campo).delete(save=False)
                setattr(config, campo, "")
        if commit:
            config.save()
        return config


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
            "assinatura_visivel",
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
        fields = ("entrega_a_partir_de", "entrega_hora_limite", "aviso_entrega",
                  "whatsapp_flutuante", "whatsapp_mensagem")
        widgets = {
            "entrega_a_partir_de": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "entrega_hora_limite": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
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
        self.fields["entrega_hora_limite"].input_formats = ["%H:%M"]
        self.fields["entrega_a_partir_de"].help_text = (
            "Aparece no checkout. Cada cidade pode ter um horário próprio."
        )


class VitrinesForm(_EstilizadoMixin, forms.ModelForm):
    """Ordem das seções da home.

    Nome da linha, cor do selo e título da vitrine saíram daqui: viraram
    cadastro em Conteúdo › Linhas de produto, onde o lojista cria quantas
    linhas quiser.
    """

    class Meta:
        model = SiteConfig
        fields = ("home_ordem",)
        widgets = {"home_ordem": forms.HiddenInput()}


class WhatsAppAutoForm(_EstilizadoMixin, forms.ModelForm):
    """Só o interruptor. O resto (QR, status, teste) é ação, não campo."""

    class Meta:
        model = SiteConfig
        fields = ("whatsapp_auto_ativo",)


class AssistenteForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = (
            "assistente_ativo", "assistente_nome", "assistente_imagem",
            "assistente_boas_vindas", "assistente_instrucoes",
            "gemini_api_key", "gemini_modelo",
        )
        widgets = {
            "assistente_instrucoes": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Ex.: só indique produtos que estão no site. "
                               "Para receita veterinária, mande falar com a loja.",
            }),
            "gemini_api_key": forms.PasswordInput(render_value=True, attrs={
                "autocomplete": "off", "placeholder": "AIza…",
            }),
        }


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
