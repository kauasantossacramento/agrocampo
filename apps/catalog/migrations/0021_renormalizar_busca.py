"""Refaz a cópia de busca com as formas no singular.

Sem esta passada, só o que for salvo daqui para a frente guarda "racao" ao
lado de "rações" — e o catálogo antigo continuaria invisível para quem digita
no plural.
"""
from django.db import migrations


def renormalizar(apps, schema_editor):
    from apps.catalog.models import normalizar_busca

    Produto = apps.get_model("catalog", "Produto")
    for produto in Produto.objects.all().only(
        "id", "nome", "resumo", "sku", "palavras_chave", "descricao", "busca_normalizada"
    ):
        produto.busca_normalizada = normalizar_busca(
            " ".join(filter(None, [
                produto.nome, produto.resumo, produto.sku,
                produto.palavras_chave, produto.descricao,
            ]))
        )
        produto.save(update_fields=["busca_normalizada"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0020_palavras_chave_e_prioridade"),
    ]

    operations = [
        # a volta é a mesma conta: o texto normalizado se refaz sozinho
        migrations.RunPython(renormalizar, renormalizar),
    ]
