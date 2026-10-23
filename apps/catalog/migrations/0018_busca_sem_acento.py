"""Preenche a cópia sem acento dos produtos que já existem.

Sem esta passada, só os produtos salvos daqui para a frente responderiam a
uma busca sem acento — e o catálogo inteiro ficaria de fora.
"""
from django.db import migrations, models


def preencher(apps, schema_editor):
    from apps.catalog.models import texto_sem_acento

    Produto = apps.get_model("catalog", "Produto")
    for produto in Produto.objects.all().only(
        "id", "nome", "resumo", "sku", "descricao", "busca_normalizada"
    ):
        produto.busca_normalizada = texto_sem_acento(
            " ".join(filter(None, [produto.nome, produto.resumo, produto.sku, produto.descricao]))
        )
        produto.save(update_fields=["busca_normalizada"])


def limpar(apps, schema_editor):
    apps.get_model("catalog", "Produto").objects.update(busca_normalizada="")


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0017_apelidos_e_nomes_de_bicho'),
    ]

    operations = [
        migrations.AddField(
            model_name='produto',
            name='busca_normalizada',
            field=models.TextField(blank=True, editable=False),
        ),
            migrations.RunPython(preencher, limpar),
    ]
