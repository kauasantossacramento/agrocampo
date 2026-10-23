"""Volta a faixa única — agora preenchendo, que é o que faltava.

No modo livre cada arte saía no seu tamanho e o carrossel mudava de altura a
cada slide. Com a faixa de volta e o ajuste em "preencher", todos ficam do
mesmo tamanho e a arte ocupa a moldura inteira, sem sobra de fundo.
"""
from django.db import migrations, models


def padronizar(apps, schema_editor):
    apps.get_model("core", "SiteConfig").objects.update(
        banners_padronizar=True, banners_ajuste="preencher",
    )


def soltar(apps, schema_editor):
    apps.get_model("core", "SiteConfig").objects.update(banners_padronizar=False)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_banner_no_tamanho_da_arte'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteconfig',
            name='banners_padronizar',
            field=models.BooleanField(default=True, help_text='Sim (padrão): todos os banners entram na mesma moldura, do mesmo tamanho — o carrossel não muda de altura a cada slide. Não: cada arte sai no próprio tamanho, e a altura varia conforme a peça. A escolha abaixo decide se a arte preenche a moldura ou aparece inteira.', verbose_name='padronizar tamanho (modo faixa)'),
        ),
            migrations.RunPython(padronizar, soltar),
    ]
