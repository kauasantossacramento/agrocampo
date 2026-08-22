from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Endereco, User

CLASSE_INPUT = "campo"


class CadastroForm(UserCreationForm):
    """Cadastro do cliente.

    O WhatsApp é obrigatório: quando falta um item do pedido, é por ele que a
    loja combina a troca. Sem número, o cliente fica esperando sem saber.
    """

    first_name = forms.CharField(label="Nome", max_length=60)
    last_name = forms.CharField(label="Sobrenome", max_length=60, required=False)
    telefone = forms.CharField(
        label="WhatsApp",
        max_length=20,
        help_text="Falamos com você por aqui se faltar algum item do pedido.",
        widget=forms.TextInput(attrs={
            "placeholder": "(75) 99999-9999",
            "inputmode": "tel",
            "data-mask": "telefone",
            "autocomplete": "tel",
        }),
    )
    aceita_contato_whatsapp = forms.BooleanField(
        label="Pode falar comigo no WhatsApp sobre os meus pedidos",
        required=False,
        initial=True,
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "telefone", "cpf")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome != "aceita_contato_whatsapp":
                campo.widget.attrs.setdefault("class", CLASSE_INPUT)
        self.fields["password1"].widget.attrs["placeholder"] = "Mínimo de 8 caracteres"

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean_telefone(self):
        telefone = (self.cleaned_data.get("telefone") or "").strip()
        digitos = "".join(c for c in telefone if c.isdigit())
        # 10 = fixo com DDD, 11 = celular com DDD
        if len(digitos) < 10:
            raise forms.ValidationError(
                "Informe o número com DDD, como (75) 99999-9999."
            )
        return telefone

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data["email"]
        usuario.username = self.cleaned_data["email"]
        usuario.telefone = self.cleaned_data.get("telefone", "")
        usuario.aceita_contato_whatsapp = self.cleaned_data.get(
            "aceita_contato_whatsapp", True
        )
        if commit:
            usuario.save()
        return usuario


class PerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "telefone", "cpf", "data_nascimento",
                  "aceita_contato_whatsapp", "aceita_marketing")
        labels = {"first_name": "Nome", "last_name": "Sobrenome"}
        widgets = {"data_nascimento": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome != "aceita_marketing":
                campo.widget.attrs.setdefault("class", CLASSE_INPUT)


class EnderecoForm(forms.ModelForm):
    """Endereço com escolha da cidade atendida — é o que define o frete."""

    class Meta:
        model = Endereco
        exclude = ("usuario",)

    def __init__(self, *args, **kwargs):
        from apps.shipping.models import Cidade, Localidade

        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome not in {"padrao", "zona_rural"}:
                campo.widget.attrs.setdefault("class", CLASSE_INPUT)
        self.fields["cep"].widget.attrs["placeholder"] = "00000-000"
        self.fields["uf"].widget.attrs["placeholder"] = "SP"

        atendidas = Cidade.objects.atendidas()
        self.fields["cidade_atendida"].queryset = atendidas
        self.fields["cidade_atendida"].label = "Cidade de entrega"
        self.fields["cidade_atendida"].empty_label = "Não está na lista"
        self.fields["cidade_atendida"].help_text = (
            "Escolha a sua cidade. Se ela não estiver aqui, ainda combinamos a "
            "entrega por WhatsApp."
        )

        self.fields["localidade"].queryset = Localidade.objects.filter(
            ativo=True, cidade__in=atendidas
        ).select_related("cidade")
        self.fields["localidade"].label = "Povoado, ilha ou bairro"
        self.fields["localidade"].empty_label = "Não é nenhum destes"
        self.fields["localidade"].help_text = (
            "Alguns lugares têm frete próprio — inclusive os que o mapa não conhece."
        )

        # nenhuma cidade cadastrada ainda: os campos só confundiriam
        if not atendidas.exists():
            self.fields.pop("cidade_atendida", None)
            self.fields.pop("localidade", None)

    def clean(self):
        dados = super().clean()
        cidade = dados.get("cidade_atendida")
        localidade = dados.get("localidade")
        if localidade and cidade and localidade.cidade_id != cidade.pk:
            self.add_error(
                "localidade",
                f"{localidade.nome} fica em {localidade.cidade.nome}, não em {cidade.nome}.",
            )
        # a cidade escolhida manda no texto do endereço: é ela que a loja entrega
        if cidade:
            dados["cidade"] = cidade.nome
            dados["uf"] = cidade.uf
        return dados
