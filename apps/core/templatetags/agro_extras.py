import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def get_item(dicionario, chave):
    """`{{ dict|get_item:chave }}` — o template do Django não indexa por variável."""
    if not dicionario:
        return []
    return dicionario.get(chave, [])


@register.simple_tag(takes_context=True)
def com_parametros(context, **novos):
    """Monta a URL atual trocando só os parâmetros informados.

    Serve às colunas que ordenam e filtram no painel: a busca e os outros
    filtros continuam valendo quando se clica no título de uma coluna.
    Valor vazio tira o parâmetro da URL.
    """
    consulta = context["request"].GET.copy()
    for chave, valor in novos.items():
        if valor in (None, ""):
            consulta.pop(chave, None)
        else:
            consulta[chave] = valor
    consulta.pop("page", None)
    texto = consulta.urlencode()
    return f"?{texto}" if texto else "?"


NEGRITO = re.compile(r"\*\*(.+?)\*\*", re.S)
# subtítulo: linha curta, sem pontuação de fim de frase, seguida de outra linha
FIM_DE_FRASE = (".", ":", ";", "!", "?", ",")


def _parece_subtitulo(linha: str, proxima: str) -> bool:
    texto = linha.strip()
    if not texto or not proxima.strip():
        return False
    if len(texto) > 70 or texto.endswith(FIM_DE_FRASE):
        return False
    # "Benefícios do alimento seco" tem poucas palavras e abre um bloco
    return len(texto.split()) <= 9


@register.filter
def texto_rico(valor):
    """Descrição do produto com negrito, sem deixar HTML passar.

    O lojista escreve `**assim**` para pôr em negrito. Além disso, uma linha
    curta sozinha antes de um parágrafo — "Benefícios do alimento seco" — já
    vira subtítulo em negrito, que é como as descrições de ração vêm escritas;
    assim o texto antigo melhora sem ninguém reeditar nada.
    """
    if not valor:
        return ""

    blocos = []
    for bloco in re.split(r"\n\s*\n", str(valor).strip()):
        linhas = bloco.split("\n")
        saida = []
        for i, linha in enumerate(linhas):
            proxima = linhas[i + 1] if i + 1 < len(linhas) else ""
            limpa = escape(linha.strip())
            if not limpa:
                continue
            if "**" not in linha and _parece_subtitulo(linha, proxima):
                limpa = f"<strong>{limpa}</strong>"
            saida.append(limpa)
        if saida:
            blocos.append("<p>" + "<br>".join(saida) + "</p>")

    html = "".join(blocos)
    html = NEGRITO.sub(lambda m: f"<strong>{m.group(1)}</strong>", html)
    return mark_safe(html)
