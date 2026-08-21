from .models import Notificacao


def notifications_context(request):
    if not request.user.is_authenticated:
        return {"notificacoes": [], "notificacoes_nao_lidas": 0}

    if request.user.e_operador:
        qs = Notificacao.objects.filter(publico=Notificacao.Publico.LOJISTA)
    else:
        qs = Notificacao.objects.do_usuario(request.user)

    return {
        "notificacoes": qs[:8],
        "notificacoes_nao_lidas": qs.nao_lidas().count(),
    }
