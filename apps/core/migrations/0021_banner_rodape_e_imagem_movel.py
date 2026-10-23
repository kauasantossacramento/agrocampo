"""Banner ganha posição de rodapé, arte de celular e 5s de padrão.

Os banners que já existem continuam com o tempo que tinham: mudar o padrão do
campo não mexe em linha gravada. Quem estava nos 6,5s herdados do padrão
antigo passa para 5s, que foi o pedido do lojista — e a volta devolve 6,5.
"""
from decimal import Decimal

import django.core.validators
from django.db import migrations, models

import apps.core.models


def cinco_segundos(apps, schema_editor):
    apps.get_model("core", "Banner").objects.filter(
        tempo_exibicao=Decimal("6.5")
    ).update(tempo_exibicao=Decimal("5"))


def seis_e_meio(apps, schema_editor):
    apps.get_model("core", "Banner").objects.filter(
        tempo_exibicao=Decimal("5")
    ).update(tempo_exibicao=Decimal("6.5"))


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_configuracao_banners_home'),
    ]

    operations = [
        migrations.AddField(
            model_name='banner',
            name='imagem_movel',
            field=models.ImageField(blank=True, help_text='Opcional. Um cartaz largo vira uma tira ilegível no celular; aqui entra a versão vertical ou quadrada. Vazio usa a de cima.', upload_to='banners/', validators=[apps.core.models.validar_tamanho_imagem], verbose_name='imagem para o celular'),
        ),
        migrations.AlterField(
            model_name='banner',
            name='posicao',
            field=models.CharField(choices=[('hero', 'Carrossel principal'), ('faixa', 'Faixa promocional'), ('secundario', 'Oferta em destaque (cartaz na home)'), ('produtos', 'Faixa de produtos (fotos com link)'), ('apresentacao', 'Vídeo ou foto de apresentação (entra no carrossel)'), ('rodape', 'Fim da página (faixa antes do rodapé)')], default='hero', max_length=20),
        ),
        migrations.AlterField(
            model_name='banner',
            name='tempo_exibicao',
            field=models.DecimalField(decimal_places=1, default=Decimal('5'), help_text='De 1 a 300 segundos por imagem. O vídeo manda no próprio tempo: o slide troca quando ele acaba, e este número vira só o limite.', max_digits=5, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(300)], verbose_name='tempo de exibição (segundos)'),
        ),
        migrations.RunPython(cinco_segundos, seis_e_meio),
    ]
