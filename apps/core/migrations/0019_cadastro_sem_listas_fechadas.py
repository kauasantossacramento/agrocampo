"""As três vitrines fixas da home dão lugar a uma seção só, que percorre as
linhas cadastradas. A ordem que o lojista já tinha salvo e as promoções
posicionadas em ouro/prata/bronze passam a apontar para essa seção.
"""
from django.db import migrations, models

ANTIGAS = ("ouro", "prata", "bronze")


def apontar_para_linhas(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    for config in SiteConfig.objects.all():
        chaves, vistas = [], set()
        for chave in (config.home_ordem or "").split(","):
            chave = chave.strip()
            chave = "linhas" if chave in ANTIGAS else chave
            if chave and chave not in vistas:
                vistas.add(chave)
                chaves.append(chave)
        config.home_ordem = ",".join(chaves)
        config.save(update_fields=["home_ordem"])

    apps.get_model("core", "PromocaoDestaque").objects.filter(
        posicao__in=ANTIGAS
    ).update(posicao="linhas")


def voltar(apps, schema_editor):
    """Devolve as três chaves no lugar da seção única."""
    SiteConfig = apps.get_model("core", "SiteConfig")
    for config in SiteConfig.objects.all():
        config.home_ordem = (config.home_ordem or "").replace(
            "linhas", "ouro,prata,bronze"
        )
        config.save(update_fields=["home_ordem"])

    apps.get_model("core", "PromocaoDestaque").objects.filter(
        posicao="linhas"
    ).update(posicao="ouro")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_linha_especial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteconfig',
            name='home_ordem',
            field=models.CharField(blank=True, default='sucessos,linhas,especies,categorias,faixas,oferta,promocoes,destaques,lancamentos,assinatura,porque,blog,newsletter,marcas', max_length=400, verbose_name='ordem das seções da home'),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='linha_bronze_nome',
            field=models.CharField(blank=True, default='Especial', editable=False, max_length=40),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='linha_ouro_nome',
            field=models.CharField(blank=True, default='Super Premium', editable=False, max_length=40),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='linha_prata_nome',
            field=models.CharField(blank=True, default='Premium', editable=False, max_length=40),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='vitrine_bronze_ativa',
            field=models.BooleanField(default=True, editable=False),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='vitrine_bronze_titulo',
            field=models.CharField(blank=True, default='Mais vendidos — Especial', editable=False, max_length=60),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='vitrine_ouro_ativa',
            field=models.BooleanField(default=True, editable=False),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='vitrine_ouro_titulo',
            field=models.CharField(blank=True, default='Mais vendidos — Super Premium', editable=False, max_length=60),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='vitrine_prata_ativa',
            field=models.BooleanField(default=True, editable=False),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='vitrine_prata_titulo',
            field=models.CharField(blank=True, default='Mais vendidos — Premium', editable=False, max_length=60),
        ),
        migrations.RunPython(apontar_para_linhas, voltar),
    ]
