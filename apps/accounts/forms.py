from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Endereco, User

CLASSE_INPUT = "campo"


class CadastroForm(UserCreationForm):
    first_name = forms.CharField(label="Nome", max_length=60)
    last_name = forms.CharField(label="Sobrenome", max_length=60, required=False)
    telefone = forms.CharField(label="Celular / WhatsApp", max_length=20, required=False)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "telefone", "cpf")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", CLASSE_INPUT)
        self.fields["password1"].widget.attrs["placeholder"] = "Mínimo de 8 caracteres"

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data["email"]
        usuario.username = self.cleaned_data["email"]
        usuario.telefone = self.cleaned_data.get("telefone", "")
        if commit:
            usuario.save()
        return usuario


class PerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "telefone", "cpf", "data_nascimento",
                  "aceita_marketing")
        labels = {"first_name": "Nome", "last_name": "Sobrenome"}
        widgets = {"data_nascimento": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome != "aceita_marketing":
                campo.widget.attrs.setdefault("class", CLASSE_INPUT)


class EnderecoForm(forms.ModelForm):
    class Meta:
        model = Endereco
        exclude = ("usuario",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome not in {"padrao", "zona_rural"}:
                campo.widget.attrs.setdefault("class", CLASSE_INPUT)
        self.fields["cep"].widget.attrs["placeholder"] = "00000-000"
        self.fields["uf"].widget.attrs["placeholder"] = "SP"
