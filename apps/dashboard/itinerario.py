"""Itinerário de entrega: os pedidos da rua, agrupados por onde ficam.

O entregador não pensa em "pedidos": pensa em ruas. Então a lista agrupa
por cidade → ilha/localidade → bairro, e dentro de cada grupo ordena pela
rua. Cada parada traz quem recebe, o telefone e o que vai na caixa — é o
papel que vai no painel do carro.
"""
from collections import OrderedDict
from datetime import date

from django.db.models import Q

from apps.orders.models import Pedido

# Pedidos que estão fisicamente a caminho de sair (ou já na rua).
STATUS_NA_RUA = {
    "separacao": [Pedido.Status.EM_SEPARACAO],
    "enviado": [Pedido.Status.ENVIADO],
    "todos": [Pedido.Status.EM_SEPARACAO, Pedido.Status.ENVIADO],
}


def _chave_cidade(pedido):
    """Nome da cidade para agrupar. Cidade atendida manda; senão, o texto."""
    endereco = pedido.endereco_entrega
    if endereco is None:
        return ("~", "Sem endereço cadastrado", False)
    cidade = endereco.cidade_atendida
    if cidade:
        # a sede vem primeiro; depois por ordem de cadastro
        return (
            ("0" if cidade.sede else "1") + f"{cidade.ordem:04d}" + cidade.nome,
            f"{cidade.nome}/{cidade.uf}",
            cidade.sede,
        )
    return ("2" + endereco.cidade, f"{endereco.cidade}/{endereco.uf} (não atendida)", False)


def _chave_localidade(pedido):
    endereco = pedido.endereco_entrega
    if endereco is None:
        return ("", "")
    if endereco.localidade:
        return ("0" + endereco.localidade.nome, endereco.localidade.nome)
    return ("1" + (endereco.bairro or ""), endereco.bairro or "Sem bairro")


def montar_itinerario(filtro="separacao", cidade_id=None, dia: date | None = None):
    """Devolve os grupos prontos para o template e os totais."""
    qs = (
        Pedido.objects.filter(status__in=STATUS_NA_RUA.get(filtro, STATUS_NA_RUA["todos"]))
        .select_related(
            "usuario", "endereco_entrega__cidade_atendida", "endereco_entrega__localidade"
        )
        .prefetch_related("itens")
        .order_by("criado_em")
    )
    if cidade_id:
        qs = qs.filter(endereco_entrega__cidade_atendida_id=cidade_id)
    if dia:
        # "do dia" = pagos até aquele dia; o que entrou depois é da próxima rota
        qs = qs.filter(Q(pago_em__date__lte=dia) | Q(pago_em__isnull=True, criado_em__date__lte=dia))

    grupos: "OrderedDict[str, dict]" = OrderedDict()
    for pedido in qs:
        chave_c, rotulo_c, sede = _chave_cidade(pedido)
        chave_l, rotulo_l = _chave_localidade(pedido)
        cidade = grupos.setdefault(
            chave_c, {"rotulo": rotulo_c, "sede": sede, "localidades": OrderedDict(), "total": 0}
        )
        local = cidade["localidades"].setdefault(chave_l, {"rotulo": rotulo_l, "paradas": []})
        local["paradas"].append(_parada(pedido))
        cidade["total"] += 1

    # ordena as chaves (a sede primeiro, ilhas antes de bairros) e as ruas
    saida = []
    for chave_c in sorted(grupos):
        cidade = grupos[chave_c]
        localidades = []
        for chave_l in sorted(cidade["localidades"]):
            local = cidade["localidades"][chave_l]
            local["paradas"].sort(key=lambda p: (p["logradouro"], p["numero"]))
            localidades.append(local)
        saida.append({**cidade, "localidades": localidades})

    total = sum(c["total"] for c in saida)
    return saida, total


def _parada(pedido):
    endereco = pedido.endereco_entrega
    itens = [
        f"{i.quantidade}x {i.descricao_completa}" for i in pedido.itens.all()
    ]
    return {
        "pedido": pedido,
        "recebe": (endereco.destinatario if endereco else "") or pedido.nome_cliente,
        "telefone": pedido.telefone_cliente or pedido.usuario.telefone,
        "logradouro": endereco.logradouro if endereco else "",
        "numero": endereco.numero if endereco else "",
        "complemento": endereco.complemento if endereco else "",
        "referencia": endereco.referencia if endereco else "",
        "endereco": endereco.linha_unica if endereco else pedido.endereco_texto,
        "zona_rural": endereco.zona_rural if endereco else False,
        "itens": itens,
        "contato_pendente": pedido.contato_pendente,
        "observacoes": pedido.observacoes,
    }
