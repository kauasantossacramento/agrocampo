"""Endpoint do chat da Silvinha. JSON puro, sem página."""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import Produto
from apps.core.models import SiteConfig

from . import services

MAX_PERGUNTA = 600


def _limite_estourado(request) -> bool:
    """Contador simples na sessão: N perguntas por hora."""
    agora = timezone.now().timestamp()
    janela = request.session.get("silvinha_janela") or [agora, 0]
    inicio, quantidade = janela
    if agora - inicio > 3600:
        inicio, quantidade = agora, 0
    if quantidade >= services.LIMITE_POR_HORA:
        return True
    request.session["silvinha_janela"] = [inicio, quantidade + 1]
    return False


@require_POST
def conversar(request):
    config = SiteConfig.load()
    if not config.assistente_ativo:
        return JsonResponse({"erro": "Assistente desligada."}, status=404)

    try:
        dados = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    pergunta = (dados.get("pergunta") or "").strip()[:MAX_PERGUNTA]
    if not pergunta:
        return JsonResponse({"erro": "Pergunta vazia."}, status=400)

    if _limite_estourado(request):
        return JsonResponse(
            {"texto": "Você já fez muitas perguntas por agora. Fale com a loja pelo WhatsApp "
                      "que a equipe continua de lá.", "ok": False},
            status=429,
        )

    historico = [
        {"papel": m.get("papel"), "texto": str(m.get("texto", ""))[:MAX_PERGUNTA]}
        for m in (dados.get("historico") or [])
        if m.get("papel") in ("usuario", "assistente")
    ]

    produto = None
    if dados.get("produto"):
        produto = get_object_or_404(Produto.objects.vitrine(), slug=dados["produto"])

    if not request.session.session_key:
        request.session.save()

    resultado = services.responder(
        sessao=request.session.session_key,
        pergunta=pergunta,
        historico=historico,
        produto=produto,
        usuario=request.user,
    )
    return JsonResponse(resultado)
