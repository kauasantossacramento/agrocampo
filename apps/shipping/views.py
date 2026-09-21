"""Página pública de entrega: onde a loja chega e quando."""
from django.shortcuts import render

from apps.core.models import SiteConfig

from .models import Cidade, RegraEntrega


def onde_entregamos(request):
    cidades = (
        Cidade.objects.atendidas()
        .prefetch_related("localidades")
        .order_by("-sede", "ordem", "nome")
    )
    return render(
        request,
        "shipping/onde_entregamos.html",
        {
            "cidades": cidades,
            "sede": cidades.filter(sede=True).first(),
            "config": SiteConfig.load(),
            "avisos": RegraEntrega.objects.filter(ativo=True, cidade__isnull=True),
        },
    )


def calcular(request):
    """Calculadora de frete da página do produto (JSON).

    Recebe cidade, localidade (opcional) e subtotal; usa a mesma regra do
    checkout, então o que aparece aqui é o que vai ser cobrado.
    """
    from decimal import Decimal, InvalidOperation
    from types import SimpleNamespace

    from django.http import JsonResponse
    from django.utils.formats import date_format

    from .models import Localidade, calcular_frete

    cidade = Cidade.objects.atendidas().filter(pk=request.GET.get("cidade") or 0).first()
    localidade = None
    if cidade and request.GET.get("localidade"):
        localidade = Localidade.objects.filter(
            pk=request.GET["localidade"], cidade=cidade, ativo=True
        ).first()
    try:
        subtotal = Decimal(str(request.GET.get("subtotal", "0")).replace(",", "."))
    except InvalidOperation:
        subtotal = Decimal("0")

    endereco = SimpleNamespace(cidade_atendida=cidade, localidade=localidade)
    resultado = calcular_frete(endereco, subtotal)
    return JsonResponse({
        "atendida": resultado["atendida"],
        "valor": f"{resultado['valor']:.2f}".replace(".", ","),
        "gratis": resultado["valor"] == 0 and resultado["atendida"],
        "prazo": date_format(resultado["prazo"], "d/m") if resultado["prazo"] else "",
        # em português, como o resto do site (strftime seguiria o locale do servidor)
        "prazo_extenso": date_format(resultado["prazo"], "l, d/m") if resultado["prazo"] else "",
        "avisos": resultado["avisos"],
    })
