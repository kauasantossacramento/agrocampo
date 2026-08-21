"""Área do cliente para gerenciar assinaturas recorrentes."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Assinatura


@login_required
def lista(request):
    assinaturas = (
        Assinatura.objects.filter(usuario=request.user)
        .select_related("produto", "cartao")
        .prefetch_related("produto__imagens", "ciclos")
    )
    return render(request, "subscriptions/lista.html", {"assinaturas": assinaturas})


@login_required
def detalhe(request, pk):
    assinatura = get_object_or_404(Assinatura, pk=pk, usuario=request.user)
    return render(
        request,
        "subscriptions/detalhe.html",
        {"assinatura": assinatura, "ciclos": assinatura.ciclos.all()},
    )


@login_required
@require_POST
def pular(request, pk):
    assinatura = get_object_or_404(Assinatura, pk=pk, usuario=request.user)
    nova_data = assinatura.pular_ciclo()
    messages.info(request, f"Entrega adiada para {nova_data.strftime('%d/%m/%Y')}.")
    return redirect("subscriptions:lista")


@login_required
@require_POST
def pausar(request, pk):
    assinatura = get_object_or_404(Assinatura, pk=pk, usuario=request.user)
    assinatura.pausar()
    messages.info(request, "Assinatura pausada. Você pode retomar quando quiser.")
    return redirect("subscriptions:lista")


@login_required
@require_POST
def retomar(request, pk):
    assinatura = get_object_or_404(Assinatura, pk=pk, usuario=request.user)
    assinatura.retomar()
    messages.success(request, "Assinatura reativada!")
    return redirect("subscriptions:lista")


@login_required
@require_POST
def cancelar(request, pk):
    assinatura = get_object_or_404(Assinatura, pk=pk, usuario=request.user)
    assinatura.cancelar(request.POST.get("motivo", "Cancelada pelo cliente"))
    messages.info(request, "Assinatura cancelada.")
    return redirect("subscriptions:lista")


@login_required
@require_POST
def alterar_frequencia(request, pk):
    assinatura = get_object_or_404(Assinatura, pk=pk, usuario=request.user)
    frequencia = int(request.POST.get("frequencia", 30))
    if frequencia in dict(Assinatura.FREQUENCIAS):
        assinatura.frequencia_dias = frequencia
        assinatura.save(update_fields=["frequencia_dias", "atualizado_em"])
        messages.success(request, f"Frequência alterada para {frequencia} dias.")
    return redirect("subscriptions:lista")
