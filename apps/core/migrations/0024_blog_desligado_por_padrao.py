"""O blog fica desligado por enquanto; o Instagram toma o lugar dele na home.

Nenhum texto é apagado: os posts continuam no banco e voltam ao ar no dia em
que o lojista remarcar a opção em Configurações › Regras da loja.
"""
from django.db import migrations, models


def desligar_blog(apps, schema_editor):
    apps.get_model("core", "SiteConfig").objects.update(blog_ativo=False)


def religar_blog(apps, schema_editor):
    apps.get_model("core", "SiteConfig").objects.update(blog_ativo=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_videos_do_instagram'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteconfig',
            name='blog_ativo',
            field=models.BooleanField(default=False, help_text='Começa desligado: a loja posta no Instagram, e o blog ficou parado. Marque para trazer de volta ao menu, ao rodapé e à home — desmarcado, as URLs respondem 404 e os textos ficam guardados, sem se perder.', verbose_name='blog ativo'),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='home_ordem',
            field=models.CharField(blank=True, default='sucessos,linhas,especies,categorias,faixas,oferta,promocoes,destaques,lancamentos,assinatura,porque,instagram,newsletter,marcas,blog', max_length=400, verbose_name='ordem das seções da home'),
        ),
            migrations.RunPython(desligar_blog, religar_blog),
    ]
