from django import template

register = template.Library()


@register.filter
def get_item(dicionario, chave):
    """`{{ dict|get_item:chave }}` — o template do Django não indexa por variável."""
    if not dicionario:
        return []
    return dicionario.get(chave, [])
