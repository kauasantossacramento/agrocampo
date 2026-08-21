"""Orquestração de pagamentos: inicia cobranças, trata webhooks e estorna.

Todo o resto do sistema fala com este módulo, nunca com o driver da Stone
diretamente.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notificacao
from apps.notifications.services import notificar, notificar_lojistas

from .gateways import DadosCartao, ErroGateway, get_gateway
from .models import Estorno, EventoWebhook, Pagamento, ProvedorPagamento


def _novo_pagamento(pedido, metodo, provedor=None, parcelas=1) -> Pagamento:
    provedor = provedor or ProvedorPagamento.ativo_padrao()
    return Pagamento.objects.create(
        pedido=pedido,
        provedor=provedor,
        metodo=metodo,
        valor=pedido.total,
        parcelas=parcelas,
        status=Pagamento.Status.PROCESSANDO,
        idempotency_key=uuid.uuid4().hex,
    )


def _aplicar_resultado(pagamento: Pagamento, resultado) -> Pagamento:
    """Copia a resposta normalizada do adquirente para o model."""
    pagamento.status = resultado.status or pagamento.status
    pagamento.referencia_externa = resultado.referencia_externa or pagamento.referencia_externa
    pagamento.mensagem = resultado.mensagem
    pagamento.codigo_retorno = resultado.codigo_retorno
    pagamento.codigo_autorizacao = resultado.codigo_autorizacao
    pagamento.nsu = resultado.nsu
    pagamento.tid = resultado.tid
    pagamento.bandeira = resultado.bandeira
    pagamento.ultimos_digitos = resultado.ultimos_digitos
    if resultado.pix_qrcode:
        pagamento.pix_qrcode = resultado.pix_qrcode
        pagamento.pix_qrcode_imagem = resultado.pix_qrcode_imagem
        pagamento.pix_expira_em = resultado.pix_expira_em
    if resultado.boleto_linha_digitavel:
        pagamento.boleto_linha_digitavel = resultado.boleto_linha_digitavel
        pagamento.boleto_url = resultado.boleto_url
    if pagamento.status == Pagamento.Status.PAGO:
        pagamento.valor_capturado = pagamento.valor
        pagamento.pago_em = timezone.now()
    pagamento.save()
    return pagamento


@transaction.atomic
def cobrar_cartao(pedido, dados_cartao: dict, parcelas=1, salvar_cartao=False) -> Pagamento:
    """Autoriza (e captura, se configurado) um pagamento com cartão."""
    provedor = ProvedorPagamento.ativo_padrao()
    pagamento = _novo_pagamento(pedido, Pagamento.Metodo.CARTAO, provedor, parcelas)
    cartao = DadosCartao(**dados_cartao)
    gateway = get_gateway(provedor)

    try:
        resultado = gateway.autorizar_cartao(pagamento, cartao, parcelas)
    except ErroGateway as exc:
        pagamento.marcar_recusado(f"Falha ao comunicar com o adquirente: {exc.mensagem}")
        return pagamento

    _aplicar_resultado(pagamento, resultado)

    if salvar_cartao and resultado.sucesso and pedido.usuario:
        _tokenizar(pedido.usuario, cartao, provedor, gateway)

    if pagamento.status in {Pagamento.Status.PAGO, Pagamento.Status.AUTORIZADO}:
        _confirmar_pedido(pedido, pagamento)
    else:
        _pagamento_recusado(pedido, pagamento)
    return pagamento


@transaction.atomic
def cobrar_pix(pedido) -> Pagamento:
    """Gera o QR Code. O pedido só avança quando o webhook confirmar."""
    provedor = ProvedorPagamento.ativo_padrao()
    pagamento = _novo_pagamento(pedido, Pagamento.Metodo.PIX, provedor)
    gateway = get_gateway(provedor)
    try:
        resultado = gateway.criar_pix(pagamento)
    except ErroGateway as exc:
        pagamento.marcar_recusado(f"Falha ao gerar Pix: {exc.mensagem}")
        return pagamento
    _aplicar_resultado(pagamento, resultado)
    pagamento.status = Pagamento.Status.PENDENTE
    pagamento.save(update_fields=["status"])
    return pagamento


@transaction.atomic
def cobrar_boleto(pedido) -> Pagamento:
    provedor = ProvedorPagamento.ativo_padrao()
    pagamento = _novo_pagamento(pedido, Pagamento.Metodo.BOLETO, provedor)
    try:
        resultado = get_gateway(provedor).criar_boleto(pagamento)
    except ErroGateway as exc:
        pagamento.marcar_recusado(f"Falha ao gerar boleto: {exc.mensagem}")
        return pagamento
    _aplicar_resultado(pagamento, resultado)
    pagamento.status = Pagamento.Status.PENDENTE
    pagamento.save(update_fields=["status"])
    return pagamento


def cobrar_assinatura(pedido, cartao_tokenizado) -> Pagamento:
    """Cobrança recorrente de um ciclo de assinatura."""
    provedor = ProvedorPagamento.ativo_padrao()
    pagamento = _novo_pagamento(pedido, Pagamento.Metodo.CARTAO, provedor)
    try:
        resultado = get_gateway(provedor).cobrar_com_token(pagamento, cartao_tokenizado.token)
    except ErroGateway as exc:
        pagamento.marcar_recusado(f"Falha na cobrança recorrente: {exc.mensagem}")
        return pagamento
    _aplicar_resultado(pagamento, resultado)
    if pagamento.liquidado:
        _confirmar_pedido(pedido, pagamento)
    return pagamento


def _tokenizar(usuario, cartao: DadosCartao, provedor, gateway):
    from .models import CartaoTokenizado

    try:
        resultado = gateway.tokenizar_cartao(usuario, cartao)
    except ErroGateway:
        return None
    if not resultado.sucesso:
        return None
    return CartaoTokenizado.objects.create(
        usuario=usuario,
        provedor=provedor,
        token=resultado.referencia_externa,
        bandeira=resultado.bandeira or cartao.bandeira,
        ultimos_digitos=resultado.ultimos_digitos or cartao.ultimos_digitos,
        nome_impresso=cartao.nome,
        validade_mes=cartao.validade_mes,
        validade_ano=cartao.validade_ano,
        padrao=not usuario.cartoes.exists(),
    )


# ---------------------------------------------------------------- pos-pagamento
def _confirmar_pedido(pedido, pagamento):
    """Pagamento aprovado → pedido entra na fila de conferência do lojista."""
    from apps.orders.models import Pedido as PedidoModel

    if pedido.status in {PedidoModel.Status.RASCUNHO, PedidoModel.Status.AGUARDANDO_PAGAMENTO}:
        pedido.mudar_status(
            PedidoModel.Status.PAGO,
            titulo="Pagamento confirmado",
            descricao=f"{pagamento.get_metodo_display()} aprovado.",
        )
    if pedido.status == PedidoModel.Status.PAGO:
        pedido.mudar_status(
            PedidoModel.Status.AGUARDANDO_APROVACAO,
            titulo="Aguardando conferência do lojista",
            descricao="A equipe está confirmando a disponibilidade em estoque.",
        )

    notificar(
        destinatario=pedido.usuario,
        tipo=Notificacao.Tipo.PAGAMENTO_CONFIRMADO,
        nivel=Notificacao.Nivel.SUCESSO,
        titulo="Pagamento confirmado",
        mensagem=f"Pedido {pedido.numero} · {pagamento.get_metodo_display()}",
        link=pedido.get_absolute_url(),
        pedido=pedido,
        email=True,
    )
    notificar_lojistas(
        tipo=Notificacao.Tipo.PEDIDO_NOVO,
        titulo="Novo pedido recebido",
        mensagem=f"{pedido.numero} · {pedido.nome_cliente} · R$ {pedido.total}",
        link=f"/painel/pedidos/{pedido.numero}/",
        pedido=pedido,
    )


def _pagamento_recusado(pedido, pagamento):
    notificar(
        destinatario=pedido.usuario,
        tipo=Notificacao.Tipo.PAGAMENTO_RECUSADO,
        nivel=Notificacao.Nivel.ERRO,
        titulo="Pagamento não aprovado",
        mensagem=pagamento.mensagem or "Tente outro cartão ou pague com Pix.",
        link=pedido.get_absolute_url(),
        pedido=pedido,
        email=True,
    )


# ---------------------------------------------------------------------- estorno
@transaction.atomic
def estornar(pagamento: Pagamento, valor=None, motivo=Estorno.Motivo.OUTRO, autor=None,
             observacao="") -> Estorno:
    """Solicita o estorno na Stone e devolve o registro criado."""
    valor = Decimal(valor) if valor is not None else pagamento.valor_estornavel
    estorno = Estorno.objects.create(
        pagamento=pagamento,
        valor=valor,
        motivo=motivo,
        observacao=observacao,
        solicitado_por=autor,
        status=Estorno.Status.PROCESSANDO,
    )
    try:
        resultado = get_gateway(pagamento.provedor).estornar(pagamento, valor)
    except ErroGateway as exc:
        estorno.status = Estorno.Status.FALHOU
        estorno.observacao = (estorno.observacao + f" | {exc.mensagem}")[:250]
        estorno.save(update_fields=["status", "observacao"])
        return estorno

    if resultado.sucesso:
        estorno.status = Estorno.Status.CONCLUIDO
        estorno.referencia_externa = resultado.referencia_externa
        estorno.concluido_em = timezone.now()
        pagamento.registrar_estorno(valor)
        pedido = pagamento.pedido
        notificar(
            destinatario=pedido.usuario,
            tipo=Notificacao.Tipo.ESTORNO,
            nivel=Notificacao.Nivel.SUCESSO,
            titulo="Estorno solicitado",
            mensagem=(
                f"R$ {valor} retorna ao seu meio de pagamento em até 5 dias úteis."
            ),
            link=pedido.get_absolute_url(),
            pedido=pedido,
            email=True,
        )
    else:
        estorno.status = Estorno.Status.FALHOU
        estorno.observacao = (estorno.observacao + f" | {resultado.mensagem}")[:250]
    estorno.save()
    return estorno


# --------------------------------------------------------------------- webhooks
def registrar_webhook(corpo: bytes, payload: dict, assinatura: str) -> EventoWebhook:
    """Persiste o evento cru antes de qualquer processamento."""
    provedor = ProvedorPagamento.ativo_padrao()
    gateway = get_gateway(provedor)
    valida = gateway.validar_webhook(corpo, assinatura)
    dados = gateway.interpretar_webhook(payload)
    return EventoWebhook.objects.create(
        provedor=provedor,
        tipo=dados.get("tipo", ""),
        referencia_externa=dados.get("referencia_externa", ""),
        assinatura=assinatura[:300],
        assinatura_valida=valida,
        payload=payload,
    )


@transaction.atomic
def processar_webhook(evento: EventoWebhook) -> EventoWebhook:
    """Aplica o efeito do evento no pagamento e no pedido correspondentes."""
    gateway = get_gateway(evento.provedor)
    dados = gateway.interpretar_webhook(evento.payload)
    referencia = dados.get("referencia_externa")

    pagamento = Pagamento.objects.filter(referencia_externa=referencia).first()
    if not pagamento:
        evento.erro = f"Pagamento não encontrado para a referência {referencia}."
        evento.processado = True
        evento.processado_em = timezone.now()
        evento.save(update_fields=["erro", "processado", "processado_em"])
        return evento

    novo_status = dados.get("status")
    if novo_status == Pagamento.Status.PAGO and not pagamento.liquidado:
        pagamento.marcar_pago(referencia, "Confirmado pelo adquirente.")
        if dados.get("e2e_id"):
            pagamento.pix_e2e_id = dados["e2e_id"]
            pagamento.save(update_fields=["pix_e2e_id"])
        _confirmar_pedido(pagamento.pedido, pagamento)
    elif novo_status == Pagamento.Status.RECUSADO:
        pagamento.marcar_recusado("Recusado pelo adquirente.")
        _pagamento_recusado(pagamento.pedido, pagamento)
    elif novo_status in {Pagamento.Status.ESTORNADO, Pagamento.Status.ESTORNO_PARCIAL}:
        valor = dados.get("valor") or pagamento.valor_estornavel
        pagamento.registrar_estorno(valor)
    elif novo_status:
        pagamento.status = novo_status
        pagamento.save(update_fields=["status", "atualizado_em"])

    evento.processado = True
    evento.processado_em = timezone.now()
    evento.save(update_fields=["processado", "processado_em"])
    return evento


def sincronizar(pagamento: Pagamento) -> Pagamento:
    """Consulta ativa — usada pelo polling da tela de Pix."""
    if not pagamento.referencia_externa:
        return pagamento
    try:
        resultado = get_gateway(pagamento.provedor).consultar(pagamento)
    except ErroGateway:
        return pagamento
    if resultado.status == Pagamento.Status.PAGO and not pagamento.liquidado:
        pagamento.marcar_pago(resultado.referencia_externa)
        _confirmar_pedido(pagamento.pedido, pagamento)
    return pagamento
