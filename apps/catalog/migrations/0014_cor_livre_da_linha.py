"""A cor da linha deixa de ser uma das cinco do código e vira cor livre.

Quem estava em "ouro", "prata"… recebe o mesmo tom em hexadecimal, então nada
muda de aparência; a partir daqui o lojista escolhe a cor que quiser.
"""
import django.core.validators
from django.db import migrations, models

EQUIVALENTES = {
    "ouro": "#C9971B",
    "prata": "#8C97A3",
    "bronze": "#A8703C",
    "verde": "#2F7D4F",
    "azul": "#1B3C8C",
}


def para_hexadecimal(apps, schema_editor):
    LinhaProduto = apps.get_model("catalog", "LinhaProduto")
    for linha in LinhaProduto.objects.all():
        linha.cor = EQUIVALENTES.get(linha.cor, "#C9971B")
        linha.save(update_fields=["cor"])


def voltar(apps, schema_editor):
    invertido = {v: k for k, v in EQUIVALENTES.items()}
    LinhaProduto = apps.get_model("catalog", "LinhaProduto")
    for linha in LinhaProduto.objects.all():
        linha.cor = invertido.get(linha.cor, "ouro")
        linha.save(update_fields=["cor"])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0013_selo_da_linha'),
    ]

    operations = [
        migrations.RunPython(para_hexadecimal, voltar),
        migrations.AlterField(
            model_name='linhaproduto',
            name='cor',
            field=models.CharField(default='#C9971B', help_text='Cor da medalha desenhada pelo site e do fio no topo do card.', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Use uma cor no formato #RRGGBB.')], verbose_name='cor do selo'),
        ),
    ]
