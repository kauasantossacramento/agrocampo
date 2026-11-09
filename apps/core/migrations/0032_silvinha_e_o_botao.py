"""A Silvinha vira o próprio botão da conversa; o balão convida a clicar.

Quem ainda estava com a frase e o tempo padrão de antes ("Oi! Quer ajuda
para escolher?", 8 s) passa para os novos. Frase escrita pelo lojista fica.
"""
from django.db import migrations, models


def atualizar(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    SiteConfig.objects.filter(silvinha_frase_espiar="Oi! Quer ajuda para escolher?").update(
        silvinha_frase_espiar="Clique em mim para tirar suas dúvidas!")
    SiteConfig.objects.filter(silvinha_espiar_segundos=8).update(silvinha_espiar_segundos=4)


def desfazer(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    SiteConfig.objects.filter(silvinha_frase_espiar="Clique em mim para tirar suas dúvidas!").update(
        silvinha_frase_espiar="Oi! Quer ajuda para escolher?")
class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_silvinha_pela_loja'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteconfig',
            name='silvinha_espiar',
            field=models.BooleanField(default=True, help_text='Alguns segundos depois de a pessoa chegar, o balão aparece ao lado dela por 10 segundos.', verbose_name='balão de convite ao lado da Silvinha'),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='silvinha_espiar_segundos',
            field=models.PositiveSmallIntegerField(default=4, verbose_name='esperar antes do balão (segundos)'),
        ),
        migrations.AlterField(
            model_name='siteconfig',
            name='silvinha_frase_espiar',
            field=models.CharField(blank=True, default='Clique em mim para tirar suas dúvidas!', max_length=90, verbose_name='frase do balão de convite'),
        ),
        migrations.RunPython(atualizar, desfazer),
    ]
