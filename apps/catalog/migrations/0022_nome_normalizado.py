"""Coluna do nome normalizada, preenchida para o catálogo que já existe."""
from django.db import migrations, models


def preencher(apps, schema_editor):
    from apps.catalog.models import normalizar_busca

    Produto = apps.get_model("catalog", "Produto")
    for produto in Produto.objects.all().only(
        "id", "nome", "palavras_chave", "nome_normalizado"
    ):
        produto.nome_normalizado = normalizar_busca(
            " ".join(filter(None, [produto.nome, produto.palavras_chave]))
        )
        produto.save(update_fields=["nome_normalizado"])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0021_renormalizar_busca'),
    ]

    operations = [
        migrations.AddField(
            model_name='produto',
            name='nome_normalizado',
            field=models.TextField(blank=True, editable=False),
        ),
            migrations.RunPython(preencher, preencher),
    ]
