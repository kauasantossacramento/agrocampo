"""Sinônimos da busca, já com o dicionário de uma loja agropet.

Pedido de 04/11/2026: "ração para cachorro", "comida de cachorro", "ração
canina" e "ração para cão" têm que achar a mesma coisa. Cada linha abaixo
vira um grupo editável no painel (Gestão › Sinônimos da busca); o lojista
apaga o que não serve e cria o que faltar.

Ficaram de fora palavras curtas que viram começo de outras ("cat" casaria
com "catarro", "pote" com "potente"): a busca compara pelo começo da
palavra, e sinônimo assim traria lixo.
"""

from django.db import migrations, models

GRUPOS = [
    "cão, cães, cachorro, cachorros, canino, canina, caninos, caninas, dog, dogs",
    "gato, gatos, gata, gatas, felino, felina, felinos, felinas, gatinho, gatinhos",
    "ração, rações, comida, alimento, alimentos, alimentação",
    "petisco, petiscos, bifinho, bifinhos, snack, snacks, biscoito, biscoitos",
    "vermífugo, vermífugos, vermifugação, verme, vermes, desverminante",
    "antipulgas, antipulga, pulga, pulgas",
    "carrapato, carrapatos, carrapaticida, carrapaticidas",
    "remédio, remédios, medicamento, medicamentos, medicação",
    "pássaro, pássaros, passarinho, passarinhos, ave, aves",
    "cavalo, cavalos, equino, equinos, égua, éguas, potro, potros",
    "boi, bois, bovino, bovinos, gado, vaca, vacas, bezerro, bezerros",
    "porco, porcos, suíno, suínos, leitão, leitões",
    "galinha, galinhas, frango, frangos, pintinho, pintinhos, poedeira, poedeiras",
    "coelho, coelhos, roedor, roedores, hamster, hamsters",
    "burro, burros, jumento, jumentos, jegue, asinino, asininos",
    "shampoo, shampoos, xampu, xampus",
    "coleira, coleiras, peitoral, peitorais",
    "areia, granulado, granulados",
    "mosca, moscas, mosquicida, mosquicidas",
    "bicheira, bicheiras, matabicheira, miíase, larvicida",
]


def semear(apps, schema_editor):
    Sinonimo = apps.get_model("catalog", "SinonimoBusca")
    for termos in GRUPOS:
        Sinonimo.objects.get_or_create(termos=termos, defaults={"ativo": True})


def desfazer(apps, schema_editor):
    apps.get_model("catalog", "SinonimoBusca").objects.filter(termos__in=GRUPOS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0022_nome_normalizado'),
    ]

    operations = [
        migrations.CreateModel(
            name='SinonimoBusca',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, verbose_name='atualizado em')),
                ('termos', models.CharField(help_text='Separe por vírgula: cão, cachorro, canino, dog. Acento, maiúscula e plural não importam.', max_length=400, verbose_name='palavras que significam a mesma coisa')),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'sinônimo da busca',
                'verbose_name_plural': 'sinônimos da busca',
                'ordering': ['termos'],
            },
        ),
        migrations.RunPython(semear, desfazer),
    ]
