"""Nome técnico vira nome de bicho, entram os apelidos de busca e o burro.

O lojista pediu nomes que o cliente usa: equino é cavalo. Só renomeia quando
o nome gravado ainda é o técnico — se alguém já tinha trocado à mão, fica
como está. O slug não muda, então `/especie/equino/` continua respondendo.

Os apelidos existem para a busca: quem digita "cachorro" não acha nada num
cadastro que diz "Cão".
"""
from django.db import migrations, models

# técnico -> (nome que o cliente usa, apelidos para a busca)
NOMES = {
    "Equino": ("Cavalo", "equino, égua, potro, haras"),
    "Bovino": ("Boi e vaca", "bovino, gado, novilho, bezerro, vaca, boi"),
    "Suíno": ("Porco", "suíno, suino, porca, leitão, leitao"),
    "Cão": ("Cão", "cachorro, cao, dog, canino, cãozinho, caozinho, filhote"),
    "Gato": ("Gato", "felino, gatinho, gata"),
    "Peixe": ("Peixe", "aquário, aquario, peixinho, pescado"),
    "Roedor": ("Roedor", "hamster, porquinho da índia, coelho, chinchila"),
    "Galinha": ("Galinha", "ave de postura, frango, pinto, aviário, aviario, poedeira"),
    "Aves": ("Aves", "pássaro, passaro, passarinho, ave, pássaros, passaros"),
}

# espécies que faltavam no cadastro
NOVAS = [
    {
        "nome": "Burro",
        "slug": "burro",
        "grupo": "rural",
        "sinonimos": "jumento, jegue, mula, muar, asinino",
        "descricao": "Ração, sal mineral e cuidados para burros, jumentos e mulas.",
    },
]


def nomear(apps, schema_editor):
    Especie = apps.get_model("catalog", "Especie")

    for tecnico, (amigavel, apelidos) in NOMES.items():
        especie = Especie.objects.filter(nome=tecnico).first()
        if not especie:
            continue
        especie.nome = amigavel
        especie.sinonimos = apelidos
        especie.save(update_fields=["nome", "sinonimos"])

    for dados in NOVAS:
        if Especie.objects.filter(slug=dados["slug"]).exists():
            continue
        # entra junto dos outros da lida rural, com card próprio na navegação
        parente = Especie.objects.filter(grupo="rural").order_by("ordem").first()
        Especie.objects.create(
            ordem=parente.ordem if parente else 0,
            destaque_home=True,
            publicado=True,
            **dados,
        )


def desnomear(apps, schema_editor):
    Especie = apps.get_model("catalog", "Especie")
    for tecnico, (amigavel, _) in NOMES.items():
        Especie.objects.filter(nome=amigavel).update(nome=tecnico, sinonimos="")
    Especie.objects.filter(slug__in=[d["slug"] for d in NOVAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0016_especies_agrupadas_em_aves'),
    ]

    operations = [
        migrations.AddField(
            model_name='especie',
            name='sinonimos',
            field=models.CharField(blank=True, help_text='Separe por vírgula: cachorro, dog, cãozinho. Entram na busca do site junto com o nome da espécie.', max_length=250, verbose_name='como o cliente também chama'),
        ),
            migrations.RunPython(nomear, desnomear),
    ]
