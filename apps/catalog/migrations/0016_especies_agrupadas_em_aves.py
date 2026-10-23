"""Os pássaros passam a aparecer como um card só: "Aves".

Nada é apagado. Cada espécie continua no banco, com os seus produtos: o que
muda é que elas se penduram numa espécie-mãe e somem da navegação. Quem
quiser filtrar ração de curió continua conseguindo, e a volta desta migração
devolve os treze cards de antes.

A galinha fica de fora de propósito — ela é criação, está em "Rural e
produção" e o lojista pediu para continuar separada.
"""
import django.db.models.deletion
from django.db import migrations, models

GRUPOS_DE_PASSARO = ("passeriforme", "psitacideo")


def agrupar_em_aves(apps, schema_editor):
    Especie = apps.get_model("catalog", "Especie")

    passaros = Especie.objects.filter(grupo__in=GRUPOS_DE_PASSARO)
    if not passaros.exists():
        return

    aves = Especie.objects.filter(slug="aves").first()
    if not aves:
        # herda a foto e a ordem do pássaro mais bem posicionado, para o card
        # não nascer sem imagem no meio dos outros
        modelo = passaros.order_by("ordem", "nome").first()
        aves = Especie.objects.create(
            nome="Aves",
            slug="aves",
            grupo="aves",
            icone=modelo.icone or "",
            imagem=modelo.imagem,
            credito_imagem=modelo.credito_imagem,
            descricao="Canários, calopsitas, periquitos, curiós e as demais aves.",
            ordem=modelo.ordem,
            destaque_home=True,
            publicado=True,
        )

    passaros.exclude(pk=aves.pk).update(agrupada_em=aves, destaque_home=False)


def desagrupar(apps, schema_editor):
    Especie = apps.get_model("catalog", "Especie")
    Especie.objects.filter(agrupada_em__slug="aves").update(
        agrupada_em=None, destaque_home=True,
    )
    Especie.objects.filter(slug="aves").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0015_lixeira_de_produtos'),
    ]

    operations = [
        migrations.AddField(
            model_name='especie',
            name='agrupada_em',
            field=models.ForeignKey(blank=True, help_text='Deixe vazio para a espécie ter card próprio. Preenchido, ela some da navegação e entra na espécie escolhida.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agrupadas', to='catalog.especie', verbose_name='agrupada em'),
        ),
        migrations.AlterField(
            model_name='especie',
            name='grupo',
            field=models.CharField(choices=[('aves', 'Aves'), ('passeriforme', 'Passeriformes'), ('psitacideo', 'Psitacídeos'), ('pet', 'Pets'), ('rural', 'Rural e produção'), ('outro', 'Outros')], default='outro', max_length=20),
        ),
            migrations.RunPython(agrupar_em_aves, desagrupar),
    ]
