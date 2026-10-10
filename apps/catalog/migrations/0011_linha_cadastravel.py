"""As linhas deixam de ser três opções no código e viram cadastro do lojista.

Nada se perde: o campo antigo é renomeado, as linhas que existiam viram
registros com o nome que o lojista já tinha dado em Configurações › Vitrines
(Super Premium, Premium, Especial) e cada produto é religado à sua linha. O
campo antigo fica no banco, sem aparecer em tela, para a volta ser possível.
"""
import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify


NOMES_PADRAO = {
    "ouro": ("Super Premium", "ouro", 0),
    "prata": ("Premium", "prata", 1),
    "bronze": ("Especial", "bronze", 2),
}


def criar_linhas(apps, schema_editor):
    LinhaProduto = apps.get_model("catalog", "LinhaProduto")
    Produto = apps.get_model("catalog", "Produto")
    SiteConfig = apps.get_model("core", "SiteConfig")

    config = SiteConfig.objects.first()
    nomes_do_lojista = {
        "ouro": getattr(config, "linha_ouro_nome", "") if config else "",
        "prata": getattr(config, "linha_prata_nome", "") if config else "",
        "bronze": getattr(config, "linha_bronze_nome", "") if config else "",
    }
    titulos = {
        "ouro": getattr(config, "vitrine_ouro_titulo", "") if config else "",
        "prata": getattr(config, "vitrine_prata_titulo", "") if config else "",
        "bronze": getattr(config, "vitrine_bronze_titulo", "") if config else "",
    }
    ativas = {
        "ouro": getattr(config, "vitrine_ouro_ativa", True) if config else True,
        "prata": getattr(config, "vitrine_prata_ativa", True) if config else True,
        "bronze": getattr(config, "vitrine_bronze_ativa", True) if config else True,
    }

    for chave, (padrao, cor, ordem) in NOMES_PADRAO.items():
        nome = (nomes_do_lojista.get(chave) or padrao).strip() or padrao
        linha = LinhaProduto.objects.create(
            nome=nome,
            slug=chave,  # mantém os links /catalogo/?linha=ouro que já circulam
            cor=cor,
            ordem=ordem,
            vitrine_titulo=titulos.get(chave) or "",
            vitrine_ativa=ativas.get(chave, True),
            ativo=True,
        )
        Produto.objects.filter(linha_antiga=chave).update(linha=linha)


def desfazer(apps, schema_editor):
    Produto = apps.get_model("catalog", "Produto")
    for produto in Produto.objects.exclude(linha=None).select_related("linha"):
        produto.linha_antiga = produto.linha.slug
        produto.save(update_fields=["linha_antiga"])
    apps.get_model("catalog", "LinhaProduto").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_linhas_proteina_estoque"),
        ("core", "0018_linha_especial"),
    ]

    operations = [
        migrations.RenameField(model_name="produto", old_name="linha", new_name="linha_antiga"),
        migrations.AlterField(
            model_name="produto",
            name="linha_antiga",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=10),
        ),
        migrations.CreateModel(
            name="LinhaProduto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("nome", models.CharField(max_length=180, verbose_name="nome")),
                ("slug", models.SlugField(blank=True, max_length=200, unique=True, verbose_name="slug")),
                ("cor", models.CharField(choices=[("ouro", "Dourado"), ("prata", "Prateado"), ("bronze", "Bronze"), ("verde", "Verde"), ("azul", "Azul")], default="ouro", max_length=10, verbose_name="cor do selo")),
                ("vitrine_titulo", models.CharField(blank=True, help_text="Vazio usa “Mais vendidos — <nome da linha>”.", max_length=60, verbose_name="título da vitrine na home")),
                ("vitrine_ativa", models.BooleanField(default=True, verbose_name="mostrar vitrine na home")),
                ("ordem", models.PositiveIntegerField(default=0, help_text="Menor aparece primeiro.")),
                ("ativo", models.BooleanField(default=True, verbose_name="em uso")),
            ],
            options={
                "verbose_name": "linha de produto",
                "verbose_name_plural": "linhas de produto",
                "ordering": ["ordem", "nome"],
            },
        ),
        migrations.AddField(
            model_name="produto",
            name="linha",
            field=models.ForeignKey(
                blank=True, null=True,
                help_text="Define o selo do produto e em qual vitrine ele aparece. Pode criar uma linha nova digitando o nome.",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="produtos", to="catalog.linhaproduto",
            ),
        ),
        migrations.RunPython(criar_linhas, desfazer),
    ]
