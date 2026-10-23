"""A loja passa a mostrar cada banner no tamanho da própria arte.

Na moldura única, arte com proporção diferente ou sobrava fundo nas laterais
(mostrando inteira) ou perdia as bordas (preenchendo). Nenhum dos dois era o
que o lojista queria: ele quer a peça ocupando a largura, inteira. No modo
livre a moldura é a própria arte.

A volta devolve a moldura padronizada.
"""
from django.db import migrations, models


def soltar_molduras(apps, schema_editor):
    apps.get_model("core", "SiteConfig").objects.update(banners_padronizar=False)


def padronizar(apps, schema_editor):
    apps.get_model("core", "SiteConfig").objects.update(banners_padronizar=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_banner_ajuste_da_moldura'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteconfig',
            name='banners_padronizar',
            field=models.BooleanField(default=False, help_text='Não (padrão): cada arte sai no próprio tamanho, ocupando a largura toda — preenche sem cortar e sem sobrar fundo. Sim: todos entram numa moldura única, e aí a escolha abaixo decide se a arte preenche (cortando) ou aparece inteira.', verbose_name='padronizar tamanho (modo faixa)'),
        ),
            migrations.RunPython(soltar_molduras, padronizar),
    ]
