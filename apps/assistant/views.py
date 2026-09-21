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


@require_POST
def acao(request):
    """Ações da compra pelo chat: entrar, cadastrar e comprar (adiciona e manda ao checkout)."""
    from django.contrib.auth import authenticate, login
    from django.middleware.csrf import get_token
    from django.urls import reverse

    from apps.accounts.forms import CadastroForm
    from apps.cart.services import mesclar_apos_login, obter_carrinho

    config = SiteConfig.load()
    if not config.assistente_ativo:
        return JsonResponse({"erro": "Assistente desligada."}, status=404)
    try:
        dados = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)
    tipo = dados.get("tipo")

    if tipo == "entrar":
        usuario = authenticate(
            request, username=(dados.get("email") or "").strip().lower(), password=dados.get("senha") or ""
        )
        if not usuario:
            return JsonResponse({"ok": False, "erro": "E-mail ou senha não conferem."})
        mesclar_apos_login(request, usuario)
        login(request, usuario)
        # o login gira o token CSRF: o chat precisa do novo para a próxima ação
        return JsonResponse({"ok": True, "nome": usuario.primeiro_nome, "csrf": get_token(request)})

    if tipo == "cadastrar":
        senha = dados.get("senha") or ""
        form = CadastroForm({
            "first_name": (dados.get("nome") or "").strip().split(" ")[0],
            "last_name": " ".join((dados.get("nome") or "").strip().split(" ")[1:]),
            "email": (dados.get("email") or "").strip().lower(),
            "telefone": dados.get("telefone") or "",
            "password1": senha, "password2": senha,
            "aceita_contato_whatsapp": True,
        })
        if not form.is_valid():
            erros = {campo: " ".join(msgs) for campo, msgs in form.errors.items()}
            return JsonResponse({"ok": False, "erros": erros})
        usuario = form.save()
        mesclar_apos_login(request, usuario)
        login(request, usuario, backend="apps.accounts.backends.EmailOrUsernameBackend")
        return JsonResponse({"ok": True, "nome": usuario.primeiro_nome, "criado": True, "csrf": get_token(request)})

    if tipo == "comprar":
        if not request.user.is_authenticated:
            return JsonResponse({"ok": False, "precisa_login": True})
        produto = get_object_or_404(Produto.objects.vitrine(), slug=dados.get("produto") or "")
        quantidade = max(1, min(int(dados.get("quantidade") or 1), 50))
        variacao = None
        if produto.tem_variacoes:
            variacao = produto.variacoes.filter(pk=dados.get("variacao") or 0, ativo=True).first() or produto.variacao_padrao
        disponivel = variacao.estoque if variacao else produto.estoque
        if disponivel < quantidade:
            return JsonResponse({"ok": False, "erro": f"Só temos {max(disponivel, 0)} em estoque."})
        assinar = int(dados.get("assinar") or 0)
        recorrente = assinar in (30, 60, 90) and produto.permite_assinatura and config.assinatura_visivel
        carrinho = obter_carrinho(request)
        carrinho.adicionar(produto, quantidade, recorrente, assinar if recorrente else None, variacao=variacao)
        como = f"assinatura a cada {assinar} dias" if recorrente else "no carrinho"
        return JsonResponse({
            "ok": True, "checkout": reverse("cart:checkout"),
            "quantidade_carrinho": carrinho.quantidade_itens,
            "mensagem": f"{quantidade}x {produto.nome} ({como}). Vamos para a entrega e o pagamento.",
        })

    return JsonResponse({"erro": "Ação desconhecida."}, status=400)
