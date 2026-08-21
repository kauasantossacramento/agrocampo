"""Converte o `icone` das categorias de emoji para a chave do SVG.

A migration 0003 trocou o significado do campo (emoji → chave de <symbol>)
mas não mexeu nos dados. Resultado: bases já existentes ficaram com `🐕`
gravado, o template montava `href="#c-🐕"`, o símbolo não existia e o ícone
simplesmente não aparecia.
"""
from django.db import migrations

# emoji antigo -> chave nova
DE_PARA = {
    "🐕": "racao",
    "🐦": "ave",
    "🚜": "rural",
    "💊": "saude",
    "🦴": "acessorio",
    "🌱": "jardim",
    "🐈": "gato",
    "🐠": "peixe",
    "🐾": "pata",
    "🐤": "ave",
    "🦜": "ave",
    "🐄": "rural",
    "🐴": "rural",
    "🐖": "rural",
    "🐓": "rural",
    "🐹": "pata",
}

# palavras no nome da categoria -> chave, para quem não tinha emoji
POR_NOME = [
    (("ração", "racao", "alimenta"), "racao"),
    (("ave", "pássaro", "passaro"), "ave"),
    (("rural", "fazenda", "pecuár", "pecuar"), "rural"),
    (("saúde", "saude", "medicament", "vermífug", "vermifug"), "saude"),
    (("acessóri", "acessori", "comedouro", "bebedouro"), "acessorio"),
    (("jardim", "casa", "horta", "semente"), "jardim"),
    (("cão", "cao", "cachorro"), "cao"),
    (("gato", "felin"), "gato"),
    (("peixe", "aquári", "aquari"), "peixe"),
]

VALIDOS = {
    "racao", "ave", "rural", "saude", "acessorio", "jardim",
    "cao", "gato", "peixe", "semente", "pata",
}


def para_frente(apps, schema_editor):
    Categoria = apps.get_model("catalog", "Categoria")

    for categoria in Categoria.objects.all():
        atual = (categoria.icone or "").strip()
        if atual in VALIDOS:
            continue

        nova = DE_PARA.get(atual)
        if not nova:
            nome = categoria.nome.lower()
            nova = next(
                (chave for termos, chave in POR_NOME if any(t in nome for t in termos)),
                "pata",
            )

        categoria.icone = nova
        categoria.save(update_fields=["icone"])


def para_tras(apps, schema_editor):
    """Volta para emoji. Perde nuance, mas não quebra nada."""
    Categoria = apps.get_model("catalog", "Categoria")
    inverso = {
        "racao": "🐕", "ave": "🐦", "rural": "🚜", "saude": "💊",
        "acessorio": "🦴", "jardim": "🌱", "cao": "🐕", "gato": "🐈",
        "peixe": "🐠", "semente": "🌱", "pata": "🐾",
    }
    for categoria in Categoria.objects.all():
        if categoria.icone in inverso:
            categoria.icone = inverso[categoria.icone]
            categoria.save(update_fields=["icone"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_avaliacao_compra_verificada")]
    operations = [migrations.RunPython(para_frente, para_tras)]
