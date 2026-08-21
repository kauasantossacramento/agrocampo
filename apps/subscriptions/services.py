"""Criação e processamento das assinaturas recorrentes."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notificacao
from apps.notifications.services import notificar
from apps.orders.models import ItemPedido, Pedido

from .models import Assinatura, CicloAssinatura


def criar_assinatura(*, usuario, produto, quantidade, frequencia_dias, preco_unitario,
                     endereco=None, cartao=None) -> Assinatura:
    """Cria (ou reativa) a assinatura de um produto para o cliente."""
    existente = Assinatura.objects.filter(
        usuario=usuario, produto=produto, status=Assinatura.Status.ATIVA
    ).first()
    if existente:
        existente.quantidade = quantidade
        existente.frequencia_dias = frequencia_dias
        existente.preco_unitario = preco_unitario
        existente.save(
            update_fields=[
                "quantidade", "frequencia_dias", "preco_unitario", "atualizado_em"
            ]
        )
        return existente

    cartao = cartao or usuario.cartoes.filter(ativo=True, padrao=True).first()
    return Assinatura.objects.create(
        usuario=usuario,
        produto=produto,
        quantidade=quantidade,
        frequencia_dias=frequencia_dias,
        preco_unitario=preco_unitario,
        endereco_entrega=endereco or usuario.endereco_padrao,
        cartao=cartao,
        proxima_entrega=timezone.localdate() + timedelta(days=frequencia_dias),
    )


@transaction.atomic
def processar_ciclo(assinatura: Assinatura) -> CicloAssinatura:
    """Cobra o cartão tokenizado e cria o pedido daquela entrega."""
    from apps.payments.services import cobrar_assinatura

    numero = assinatura.ciclos.count() + 1
    ciclo = CicloAssinatura.objects.create(
        assinatura=assinatura,
        numero_ciclo=numero,
        data_prevista=assinatura.proxima_entrega,
        valor=assinatura.total_por_ciclo,
        status=CicloAssinatura.Status.COBRANDO,
        tentativas=1,
    )

    if not assinatura.cartao:
        return _falhar(ciclo, assinatura, "Nenhum cartão salvo para a cobrança recorrente.")

    if assinatura.produto.estoque < assinatura.quantidade:
        return _falhar(ciclo, assinatura, "Produto sem estoque para esta entrega.")

    pedido = _pedido_do_ciclo(assinatura)
    ciclo.pedido = pedido

    pagamento = cobrar_assinatura(pedido, assinatura.cartao)
    ciclo.processado_em = timezone.now()

    if pagamento.liquidado:
        ciclo.status = CicloAssinatura.Status.PAGO
        assinatura.falhas_consecutivas = 0
        assinatura.proxima_entrega = assinatura.proxima_entrega + timedelta(
            days=assinatura.frequencia_dias
        )
        assinatura.status = Assinatura.Status.ATIVA
        assinatura.save(
            update_fields=[
                "falhas_consecutivas", "proxima_entrega", "status", "atualizado_em"
            ]
        )
        ciclo.save()
        notificar(
            destinatario=assinatura.usuario,
            tipo=Notificacao.Tipo.ASSINATURA_RENOVADA,
            nivel=Notificacao.Nivel.SUCESSO,
            titulo="Assinatura renovada",
            mensagem=(
                f"{assinatura.produto.nome} · próxima entrega em "
                f"{assinatura.frequencia_dias} dias."
            ),
            link=pedido.get_absolute_url(),
            pedido=pedido,
            email=True,
        )
        return ciclo

    return _falhar(ciclo, assinatura, pagamento.mensagem or "Cobrança recusada.")


def _pedido_do_ciclo(assinatura) -> Pedido:
    endereco = assinatura.endereco_entrega or assinatura.usuario.endereco_padrao
    usuario = assinatura.usuario
    pedido = Pedido.objects.create(
        usuario=usuario,
        status=Pedido.Status.AGUARDANDO_PAGAMENTO,
        nome_cliente=usuario.get_full_name() or usuario.primeiro_nome,
        email_cliente=usuario.email,
        telefone_cliente=usuario.telefone,
        endereco_entrega=endereco,
        endereco_texto=endereco.linha_unica if endereco else "",
        assinatura=assinatura,
    )
    ItemPedido.objects.create(
        pedido=pedido,
        produto=assinatura.produto,
        nome_produto=assinatura.produto.nome,
        sku=assinatura.produto.sku,
        quantidade=assinatura.quantidade,
        preco_unitario=assinatura.preco_unitario,
        preco_cheio=assinatura.produto.preco_atual,
        recorrente=True,
        frequencia_dias=assinatura.frequencia_dias,
    )
    pedido.recalcular()
    return pedido


def _falhar(ciclo, assinatura, motivo) -> CicloAssinatura:
    ciclo.status = CicloAssinatura.Status.FALHOU
    ciclo.erro = motivo[:250]
    ciclo.processado_em = timezone.now()
    ciclo.save()

    assinatura.falhas_consecutivas += 1
    assinatura.status = (
        Assinatura.Status.CANCELADA
        if assinatura.falhas_consecutivas >= 3
        else Assinatura.Status.INADIMPLENTE
    )
    if assinatura.status == Assinatura.Status.CANCELADA:
        assinatura.cancelada_em = timezone.now()
        assinatura.motivo_cancelamento = "3 falhas consecutivas de cobrança."
    else:
        # nova tentativa em 3 dias
        assinatura.proxima_entrega = timezone.localdate() + timedelta(days=3)
    assinatura.save()

    notificar(
        destinatario=assinatura.usuario,
        tipo=Notificacao.Tipo.ASSINATURA_FALHOU,
        nivel=Notificacao.Nivel.ALERTA,
        titulo="Não conseguimos renovar sua assinatura",
        mensagem=motivo,
        link="/assinaturas/",
        email=True,
    )
    return ciclo


def processar_vencidas():
    """Roda periodicamente (cron/celery): processa todas as entregas do dia."""
    hoje = timezone.localdate()
    vencidas = Assinatura.objects.filter(
        status__in=[Assinatura.Status.ATIVA, Assinatura.Status.INADIMPLENTE],
        proxima_entrega__lte=hoje,
    ).select_related("produto", "usuario", "cartao")
    return [processar_ciclo(a) for a in vencidas]
