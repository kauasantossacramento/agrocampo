"""Regras de negócio dos pedidos: criação a partir do carrinho e decisão do lojista."""
from django.db import transaction

from apps.notifications.models import Notificacao
from apps.notifications.services import alertar_estoque_baixo, notificar

from .models import EventoPedido, ItemPedido, Pedido


class EstoqueInsuficiente(Exception):
    def __init__(self, itens):
        self.itens = itens
        nomes = ", ".join(i.produto.nome for i in itens)
        super().__init__(f"Sem estoque suficiente para: {nomes}")


@transaction.atomic
def criar_pedido_do_carrinho(carrinho, usuario, endereco=None, observacoes="") -> Pedido:
    """Congela o carrinho em um pedido. Não baixa estoque — isso é na aprovação."""
    if carrinho.vazio:
        raise ValueError("Carrinho vazio.")

    indisponiveis = [i for i in carrinho.linhas if not i.disponivel]
    if indisponiveis:
        raise EstoqueInsuficiente(indisponiveis)

    endereco = endereco or usuario.endereco_padrao
    pedido = Pedido.objects.create(
        usuario=usuario,
        status=Pedido.Status.AGUARDANDO_PAGAMENTO,
        nome_cliente=usuario.get_full_name() or usuario.primeiro_nome,
        email_cliente=usuario.email,
        telefone_cliente=usuario.telefone,
        endereco_entrega=endereco,
        endereco_texto=endereco.linha_unica if endereco else "",
        frete=carrinho.frete,
        desconto=carrinho.desconto_cupom,
        cupom=carrinho.cupom.codigo if carrinho.cupom else "",
        observacoes=observacoes,
    )

    for linha in carrinho.linhas:
        ItemPedido.objects.create(
            pedido=pedido,
            produto=linha.produto,
            nome_produto=linha.produto.nome,
            sku=linha.produto.sku,
            quantidade=linha.quantidade,
            preco_unitario=linha.preco_unitario,
            preco_cheio=linha.preco_cheio,
            recorrente=linha.recorrente,
            frequencia_dias=linha.frequencia_dias,
        )

    pedido.recalcular()
    if carrinho.cupom:
        type(carrinho.cupom).objects.filter(pk=carrinho.cupom.pk).update(
            usos=carrinho.cupom.usos + 1
        )

    EventoPedido.objects.create(
        pedido=pedido,
        status_novo=pedido.status,
        titulo="Pedido criado",
        descricao="Aguardando o pagamento.",
        autor=usuario,
    )
    return pedido


@transaction.atomic
def aprovar_pedido(pedido: Pedido, lojista) -> Pedido:
    """O lojista confirmou o estoque: baixa as unidades e avança o pedido."""
    faltantes = pedido.itens_indisponiveis
    if faltantes:
        raise EstoqueInsuficiente(faltantes)

    pedido.mudar_status(
        Pedido.Status.APROVADO,
        autor=lojista,
        titulo="Pedido aprovado",
        descricao="Disponibilidade confirmada pelo lojista.",
    )

    for item in pedido.itens.select_related("produto"):
        if item.baixado_do_estoque:
            continue
        item.produto.baixar_estoque(
            item.quantidade, motivo="Venda", pedido=pedido.numero
        )
        item.baixado_do_estoque = True
        item.save(update_fields=["baixado_do_estoque"])
        if item.produto.estoque <= item.produto.estoque_minimo:
            alertar_estoque_baixo(item.produto)

    pedido.mudar_status(
        Pedido.Status.EM_SEPARACAO,
        autor=lojista,
        titulo="Em separação",
        descricao="Seu pedido está sendo preparado para envio.",
    )

    notificar(
        destinatario=pedido.usuario,
        tipo=Notificacao.Tipo.PEDIDO_APROVADO,
        nivel=Notificacao.Nivel.SUCESSO,
        titulo="Pedido aprovado!",
        mensagem=f"Seu pedido {pedido.numero} foi aprovado e está em separação.",
        link=pedido.get_absolute_url(),
        pedido=pedido,
        email=True,
    )
    _criar_assinaturas(pedido)
    return pedido


@transaction.atomic
def recusar_pedido(pedido: Pedido, lojista, motivo="Produto sem estoque") -> Pedido:
    """Recusa por indisponibilidade: notifica e habilita sugestões/estorno."""
    pedido.motivo_recusa = motivo
    pedido.save(update_fields=["motivo_recusa"])
    pedido.mudar_status(
        Pedido.Status.RECUSADO,
        autor=lojista,
        titulo="Pedido não confirmado",
        descricao=motivo,
    )
    notificar(
        destinatario=pedido.usuario,
        tipo=Notificacao.Tipo.PEDIDO_RECUSADO,
        nivel=Notificacao.Nivel.ERRO,
        titulo="Não conseguimos confirmar seu pedido",
        mensagem=f"{motivo}. Veja produtos similares ou solicite o estorno.",
        link=pedido.get_absolute_url(),
        pedido=pedido,
        email=True,
    )
    return pedido


@transaction.atomic
def marcar_enviado(pedido: Pedido, lojista, codigo_rastreio="") -> Pedido:
    pedido.codigo_rastreio = codigo_rastreio
    pedido.save(update_fields=["codigo_rastreio"])
    pedido.mudar_status(
        Pedido.Status.ENVIADO,
        autor=lojista,
        titulo="Pedido enviado",
        descricao=f"Rastreio: {codigo_rastreio}" if codigo_rastreio else "",
    )
    notificar(
        destinatario=pedido.usuario,
        tipo=Notificacao.Tipo.PEDIDO_ENVIADO,
        nivel=Notificacao.Nivel.INFO,
        titulo="Seu pedido saiu para entrega",
        mensagem=f"Pedido {pedido.numero} a caminho.",
        link=pedido.get_absolute_url(),
        pedido=pedido,
        email=True,
    )
    return pedido


def devolver_estoque(pedido: Pedido, motivo="Pedido cancelado"):
    """Repõe as unidades já baixadas — usado em cancelamento e estorno."""
    for item in pedido.itens.select_related("produto").filter(baixado_do_estoque=True):
        item.produto.repor_estoque(item.quantidade, motivo=motivo, pedido=pedido.numero)
        item.baixado_do_estoque = False
        item.save(update_fields=["baixado_do_estoque"])


def _criar_assinaturas(pedido: Pedido):
    """Itens recorrentes viram assinaturas quando o primeiro pedido é aprovado."""
    from apps.subscriptions.services import criar_assinatura

    if pedido.assinatura_id:  # pedido gerado por um ciclo: não recria
        return
    for item in pedido.itens.filter(recorrente=True).select_related("produto"):
        criar_assinatura(
            usuario=pedido.usuario,
            produto=item.produto,
            quantidade=item.quantidade,
            frequencia_dias=item.frequencia_dias or 30,
            preco_unitario=item.preco_unitario,
            endereco=pedido.endereco_entrega,
        )
