"""A faixa promocional ganha lugar na home, logo depois do "Por que comprar".

A posição "Faixa promocional" já existia no cadastro de banners, mas não era
desenhada em lugar nenhum: o lojista podia escolhê-la e nada aparecia. Agora
ela é uma seção da home como as outras, e esta migração a coloca na ordem de
quem já tinha uma ordem salva — sem isso, uma config antiga jogaria a faixa
para o fim da página.
"""
from django.db import migrations, models


def encaixar(apps, schema_editor):
    """Põe `faixa_banner` depois de `porque` na ordem já salva."""
    SiteConfig = apps.get_model("core", "SiteConfig")
    for config in SiteConfig.objects.all():
        chaves = [c.strip() for c in (config.home_ordem or "").split(",") if c.strip()]
        if not chaves or "faixa_banner" in chaves:
            continue
        if "porque" in chaves:
            chaves.insert(chaves.index("porque") + 1, "faixa_banner")
        else:
            chaves.append("faixa_banner")
        config.home_ordem = ",".join(chaves)
        config.save(update_fields=["home_ordem"])


def desencaixar(apps, schema_editor):
    """Tira a chave da ordem salva — a seção volta a não existir."""
    SiteConfig = apps.get_model("core", "SiteConfig")
    for config in SiteConfig.objects.all():
        chaves = [c.strip() for c in (config.home_ordem or "").split(",") if c.strip()]
        if "faixa_banner" not in chaves:
            continue
        config.home_ordem = ",".join(c for c in chaves if c != "faixa_banner")
        config.save(update_fields=["home_ordem"])


class Migration(migrations.Migration):

    dependencies = [("core", "0027_faixa_unica_de_novo")]

    operations = [
        migrations.AlterField(
            model_name="siteconfig",
            name="home_ordem",
            field=models.CharField(
                blank=True,
                default="sucessos,linhas,especies,categorias,faixas,oferta,"
                        "promocoes,destaques,lancamentos,assinatura,porque,"
                        "faixa_banner,instagram,newsletter,marcas,blog",
                max_length=400,
                verbose_name="ordem das seções da home",
            ),
        ),
        migrations.AlterField(
            model_name="banner",
            name="posicao",
            field=models.CharField(
                choices=[
                    ("hero", "Carrossel principal"),
                    ("faixa", "Faixa promocional (cartaz entre as seções)"),
                    ("secundario", "Oferta em destaque (cartaz na home)"),
                    ("produtos", "Faixa de produtos (fotos com link)"),
                    ("apresentacao", "Vídeo ou foto de apresentação (entra no carrossel)"),
                    ("rodape", "Fim da página (faixa antes do rodapé)"),
                ],
                default="hero",
                max_length=20,
            ),
        ),
        migrations.RunPython(encaixar, desencaixar),
    ]
