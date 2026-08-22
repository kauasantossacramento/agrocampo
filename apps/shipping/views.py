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
