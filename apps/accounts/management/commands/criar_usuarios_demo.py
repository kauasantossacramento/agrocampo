"""Cria os três perfis de acesso para demonstrar a loja.

    python manage.py criar_usuarios_demo

Use apenas em desenvolvimento — as senhas são públicas.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

SENHA = "agrocampo123"


class Command(BaseCommand):
    help = "Cria admin, lojista e cliente de demonstração."

    def handle(self, *args, **opcoes):
        admin, criado = User.objects.get_or_create(
            email="admin@agrocampo.com.br",
            defaults={"username": "admin@agrocampo.com.br", "first_name": "Admin",
                      "papel": User.Papel.ADMIN, "is_staff": True, "is_superuser": True},
        )
        if criado:
            admin.set_password(SENHA)
            admin.save()

        lojista, criado = User.objects.get_or_create(
            email="lojista@agrocampo.com.br",
            defaults={"username": "lojista@agrocampo.com.br", "first_name": "Lojista",
                      "papel": User.Papel.LOJISTA, "is_staff": True},
        )
        if criado:
            lojista.set_password(SENHA)
            lojista.save()

        cliente, criado = User.objects.get_or_create(
            email="cliente@agrocampo.com.br",
            defaults={"username": "cliente@agrocampo.com.br", "first_name": "Maria",
                      "last_name": "Silva", "telefone": "(14) 99999-0000"},
        )
        if criado:
            cliente.set_password(SENHA)
            cliente.save()
            cliente.enderecos.create(
                apelido="Sítio Boa Vista", destinatario="Maria Silva", cep="17300-000",
                logradouro="Estrada Vicinal Km 12", numero="s/n", bairro="Zona Rural",
                cidade="Dois Córregos", uf="SP", zona_rural=True, padrao=True,
                referencia="Portão azul depois da ponte",
            )

        self.stdout.write(self.style.SUCCESS("Usuários de demonstração prontos:"))
        for papel, email in [
            ("Admin  ", "admin@agrocampo.com.br"),
            ("Lojista", "lojista@agrocampo.com.br"),
            ("Cliente", "cliente@agrocampo.com.br"),
        ]:
            self.stdout.write(f"  {papel} · {email} · senha: {SENHA}")
