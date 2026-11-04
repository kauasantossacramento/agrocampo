"""Checkout de pagamento, acompanhamento do Pix e webhooks dos adquirentes."""
import base64
import json
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.documentos import cpf_valido, formatar_cpf
from apps.orders.models import Pedido

from .gateways import get_gateway
from .models import Pagamento, ProvedorPagamento
from .services import (
    cobrar_boleto,
    cobrar_cartao,
    cobrar_pix,
    processar_webhook,
    registrar_webhook,
    sincronizar,
)


@never_cache
@login_required
def checkout(request, numero):
    """Escolha do método e submissão do pagamento."""
    pedido = get_object_or_404(Pedido, numero=numero, usuario=request.user)
    provedor = ProvedorPagamento.ativo_padrao()

    if pedido.status not in {
        Pedido.Status.AGUARDANDO_PAGAMENTO,
        Pedido.Status.RASCUNHO,
    }:
        return redirect(pedido.get_absolute_url())

    # O adquirente recusa a cobrança sem o CPF de quem compra, e o CPF é
    # opcional no cadastro. Pedido aqui, uma vez só: fica salvo no perfil.
    pede_cpf = get_gateway(provedor).exige_documento and not cpf_valido(
        request.user.cpf
    )

    if request.method == "POST":
        metodo = request.POST.get("metodo", Pagamento.Metodo.PIX)

        if pede_cpf:
            cpf = request.POST.get("comprador_cpf", "")
            if not cpf_valido(cpf):
                messages.error(
                    request,
                    "Informe um CPF válido. O banco exige o CPF de quem compra "
                    "para gerar o pagamento.",
                )
                return redirect("payments:checkout", numero=numero)
            request.user.cpf = formatar_cpf(cpf)
            request.user.save(update_fields=["cpf"])

        if metodo == Pagamento.Metodo.CARTAO:
            faltando = [
                campo
                for campo in ("numero", "nome", "validade", "cvv")
                if not request.POST.get(f"cartao_{campo}")
            ]
            if faltando:
                messages.error(request, "Preencha todos os dados do cartão.")
                return redirect("payments:checkout", numero=numero)

            validade = request.POST["cartao_validade"].replace(" ", "")
            mes, _, ano = validade.partition("/")
            try:
                mes_int, ano_int = int(mes), int(ano)
            except ValueError:
                messages.error(request, "Validade inválida. Use o formato MM/AA.")
                return redirect("payments:checkout", numero=numero)
            if ano_int < 100:
                ano_int += 2000

            pagamento = cobrar_cartao(
                pedido,
                {
                    "numero": request.POST["cartao_numero"].replace(" ", ""),
                    "nome": request.POST["cartao_nome"],
                    "validade_mes": mes_int,
                    "validade_ano": ano_int,
                    "cvv": request.POST["cartao_cvv"],
                    "cpf_titular": request.POST.get("cartao_cpf", ""),
                },
                parcelas=int(request.POST.get("parcelas", 1)),
                salvar_cartao=request.POST.get("salvar_cartao") == "1"
                or pedido.tem_recorrencia,
            )
            if pagamento.status in {Pagamento.Status.PAGO, Pagamento.Status.AUTORIZADO}:
                return redirect(pedido.get_absolute_url())
            messages.error(request, pagamento.mensagem or "Pagamento não aprovado.")
            return redirect("payments:checkout", numero=numero)

        if metodo == Pagamento.Metodo.PIX:
            pagamento = cobrar_pix(pedido)
            return redirect("payments:pix", pagamento_id=pagamento.pk)

        if metodo == Pagamento.Metodo.BOLETO:
            pagamento = cobrar_boleto(pedido)
            return redirect(pedido.get_absolute_url())

    return render(
        request,
        "payments/checkout.html",
        {
            "pedido": pedido,
            "provedor": provedor,
            "metodos": provedor.metodos_disponiveis(),
            "parcelas": provedor.parcelas_disponiveis(pedido.total),
            "cartoes": request.user.cartoes.filter(ativo=True),
            "pede_cpf": pede_cpf,
        },
    )


@never_cache
@login_required
def pix(request, pagamento_id):
    """Tela do QR Code, com polling até a confirmação."""
    pagamento = get_object_or_404(
        Pagamento, pk=pagamento_id, pedido__usuario=request.user
    )
    return render(request, "payments/pix.html", {"pagamento": pagamento, "pedido": pagamento.pedido})


@login_required
def status_pagamento(request, pagamento_id):
    """Endpoint consultado pelo polling da tela de Pix."""
    pagamento = get_object_or_404(
        Pagamento, pk=pagamento_id, pedido__usuario=request.user
    )
    if not pagamento.liquidado:
        sincronizar(pagamento)
    return JsonResponse(
        {
            "status": pagamento.status,
            "rotulo": pagamento.get_status_display(),
            "pago": pagamento.liquidado,
            "expirado": pagamento.pix_expirado,
            "url_pedido": pagamento.pedido.get_absolute_url(),
        }
    )


@csrf_exempt
@require_POST
def webhook(request):
    """Recebe as notificações da Stone.

    O evento é sempre persistido antes de ser processado — se algo falhar,
    dá para reprocessar pelo admin sem perder a notificação.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponse("payload inválido", status=400)

    assinatura = (
        request.headers.get("X-Stone-Signature")
        or request.headers.get("Stone-Signature")
        or request.headers.get("X-Signature")
        or ""
    )
    evento = registrar_webhook(request.body, payload, assinatura)

    if not evento.assinatura_valida:
        evento.erro = "Assinatura inválida."
        evento.save(update_fields=["erro"])
        return HttpResponse("assinatura inválida", status=401)

    processar_webhook(evento)
    return JsonResponse({"recebido": True, "evento": evento.pk})


@csrf_exempt
@require_POST
def webhook_cielo(request):
    """Recebe o Post de Notificação da Cielo.

    A Cielo manda só `PaymentId` e `ChangeType` — ela avisa que algo mudou,
    não o que ficou. Quem descobre o estado real é o driver, consultando a
    API com as credenciais da loja; por isso não há assinatura para conferir
    aqui, e confiar no aviso sem consultar é que seria inseguro.

    A Cielo aceita JSON ou formulário, dependendo de como a conta foi
    configurada no portal — então os dois formatos são lidos.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = request.POST.dict()

    if not payload.get("PaymentId"):
        return HttpResponse("sem PaymentId", status=400)

    evento = registrar_webhook(request.body, payload, assinatura="")
    processar_webhook(evento)
    # a Cielo reenvia enquanto não receber 200
    return JsonResponse({"recebido": True, "evento": evento.pk})


@csrf_exempt
@require_POST
def webhook_pagarme(request):
    """Recebe a notificação da Pagar.me.

    A Pagar.me não assina o corpo. O que ela oferece é um usuário e senha
    Basic no endereço cadastrado no painel dela — quando o lojista
    preencher os dois campos aqui, a loja passa a recusar quem não mandar
    o cabeçalho. Vazios, a porta fica aberta, e quem garante a verdade é a
    consulta que o driver faz em seguida: o aviso diz que algo mudou, a
    API diz o que ficou.
    """
    provedor = ProvedorPagamento.ativo_padrao()
    if not _basic_confere(request, provedor):
        return HttpResponse("não autorizado", status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponse("payload inválido", status=400)

    if not payload.get("type"):
        return HttpResponse("sem tipo de evento", status=400)

    evento = registrar_webhook(request.body, payload, assinatura="")
    processar_webhook(evento)
    # a Pagar.me reenvia enquanto não receber 2xx
    return JsonResponse({"recebido": True, "evento": evento.pk})


def _basic_confere(request, provedor) -> bool:
    """Confere o Basic do webhook, quando o lojista cadastrou um."""
    usuario = provedor.pagarme_webhook_usuario
    senha = provedor.pagarme_webhook_senha
    if not usuario and not senha:
        return True

    cabecalho = request.headers.get("Authorization", "")
    if not cabecalho.lower().startswith("basic "):
        return False
    try:
        cru = base64.b64decode(cabecalho[6:].strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    recebido_usuario, _, recebido_senha = cru.partition(":")
    # compare_digest para a resposta não vazar o tamanho do acerto
    return secrets.compare_digest(recebido_usuario, usuario) and secrets.compare_digest(
        recebido_senha, senha
    )


@login_required
@require_POST
def simular_pix(request, pagamento_id):
    """Atalho de desenvolvimento: confirma um Pix sem o webhook real da Stone."""
    pagamento = get_object_or_404(
        Pagamento, pk=pagamento_id, pedido__usuario=request.user
    )
    if pagamento.provedor.driver != ProvedorPagamento.Driver.SIMULADO:
        raise Http404("Disponível apenas no provedor simulado.")

    from .services import _confirmar_pedido

    pagamento.marcar_pago(pagamento.referencia_externa, "Pix confirmado (simulação).")
    _confirmar_pedido(pagamento.pedido, pagamento)
    messages.success(request, "Pix confirmado!")
    return redirect(pagamento.pedido.get_absolute_url())
