"""Usuário customizado (login por e-mail) e endereços de entrega."""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.models import TimeStampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email)
        extra.setdefault("username", email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superusuário precisa de is_staff=True.")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Cliente ou operador da loja. O e-mail é o identificador de login."""

    class Papel(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        LOJISTA = "lojista", "Lojista"
        ADMIN = "admin", "Administrador"

    email = models.EmailField("e-mail", unique=True)
    cpf = models.CharField("CPF", max_length=14, blank=True)
    telefone = models.CharField(
        "celular / WhatsApp", max_length=20, blank=True,
        help_text="É por aqui que a loja avisa sobre falta de produto e entrega.",
    )
    aceita_contato_whatsapp = models.BooleanField(
        "pode ser chamado no WhatsApp", default=True,
        help_text="Para falar sobre o pedido quando faltar algum item.",
    )
    data_nascimento = models.DateField(null=True, blank=True)
    papel = models.CharField(max_length=20, choices=Papel.choices, default=Papel.CLIENTE)
    aceita_marketing = models.BooleanField("aceita receber ofertas", default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def whatsapp_url(self):
        """Link para a loja chamar o cliente. Vazio se não tem número ou não quer."""
        numero = "".join(c for c in self.telefone if c.isdigit())
        if not numero or not self.aceita_contato_whatsapp:
            return ""
        if not numero.startswith("55"):
            numero = "55" + numero
        return f"https://wa.me/{numero}"

    @property
    def primeiro_nome(self):
        return self.first_name or self.email.split("@")[0]

    @property
    def e_operador(self):
        return self.is_staff or self.papel in {self.Papel.LOJISTA, self.Papel.ADMIN}

    @property
    def endereco_padrao(self):
        return self.enderecos.filter(padrao=True).first() or self.enderecos.first()


class Endereco(TimeStampedModel):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enderecos")
    apelido = models.CharField(max_length=60, default="Casa")
    destinatario = models.CharField(max_length=120)
    cep = models.CharField("CEP", max_length=9)
    logradouro = models.CharField(max_length=180)
    numero = models.CharField(max_length=20)
    complemento = models.CharField(max_length=80, blank=True)
    bairro = models.CharField(max_length=90)
    cidade = models.CharField(max_length=90)
    uf = models.CharField("UF", max_length=2)
    referencia = models.CharField(
        max_length=180, blank=True, help_text="Ponto de referência — útil na zona rural."
    )
    zona_rural = models.BooleanField(default=False)
    cidade_atendida = models.ForeignKey(
        "shipping.Cidade", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enderecos", verbose_name="cidade atendida",
        help_text="Define o frete e os dias de entrega.",
    )
    localidade = models.ForeignKey(
        "shipping.Localidade", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enderecos",
        help_text="Ilha, povoado ou bairro com frete próprio.",
    )
    padrao = models.BooleanField("endereço padrão", default=False)

    class Meta:
        ordering = ["-padrao", "-criado_em"]
        verbose_name = "endereço"
        verbose_name_plural = "endereços"

    def __str__(self):
        return f"{self.apelido} — {self.cidade}/{self.uf}"

    @property
    def atendido(self) -> bool:
        return bool(self.cidade_atendida and self.cidade_atendida.ativo)

    @property
    def linha_unica(self):
        partes = [f"{self.logradouro}, {self.numero}"]
        if self.complemento:
            partes.append(self.complemento)
        partes += [self.bairro, f"{self.cidade}/{self.uf}", self.cep]
        return " · ".join(partes)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.padrao:
            Endereco.objects.filter(usuario=self.usuario).exclude(pk=self.pk).update(
                padrao=False
            )
