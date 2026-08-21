from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notificacao


def _queryset(usuario):
    if usuario.e_operador:
        return Notificacao.objects.filter(publico=Notificacao.Publico.LOJISTA)
    return Notificacao.objects.do_usuario(usuario)


@login_required
def lista(request):
    return render(request, "notifications/lista.html", {"itens": _queryset(request.user)[:50]})


@login_required
@require_POST
def marcar_lida(request, pk):
    notificacao = get_object_or_404(_queryset(request.user), pk=pk)
    notificacao.marcar_lida()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(notificacao.link or "notifications:lista")


@login_required
@require_POST
def marcar_todas(request):
    _queryset(request.user).nao_lidas().update(lida_em=timezone.now())
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(request.META.get("HTTP_REFERER", "notifications:lista"))
