"""Registro e alerta de erros do servidor.

Dois tipos de erro chegam aqui, por portas diferentes:

* **500** — exceção dentro do Django. O próprio Django avisa pelo sinal
  `got_request_exception`, com o rastro em mãos.
* **502/503/504** — o Django nem chegou a responder: estava reiniciando,
  travado ou fora do ar. Quem vê é o nginx, que anota a linha num arquivo
  separado; o cron lê esse arquivo (`vigiar_erros`).

Erro repetido não vira linha nova: a assinatura (tipo + exceção + onde
estourou) agrupa as ocorrências, e o alerta por e-mail sai no máximo uma vez
por hora para cada assinatura. Um erro que se repete mil vezes numa manhã
manda um e-mail, não mil.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import traceback
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

log = logging.getLogger(__name__)

# entre dois e-mails sobre o mesmo erro
INTERVALO_ALERTA = timedelta(hours=1)

# linha do log "combined" do nginx
LINHA_NGINX = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<quando>[^\]]+)\] '
    r'"(?P<metodo>[A-Z]+) (?P<caminho>\S+)[^"]*" (?P<status>\d{3}) '
)

MOTIVO_BORDA = {
    "502": "O site não respondeu ao nginx (reiniciando ou fora do ar).",
    "503": "O site recusou a requisição por estar indisponível.",
    "504": "O site demorou demais para responder.",
}


def _assinatura(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode()).hexdigest()


def _onde_estourou(rastro) -> str:
    """Arquivo e linha do último quadro do projeto — o lugar que importa.

    O último quadro de todos costuma ser do Django ou de uma biblioteca; o
    que interessa é a última linha nossa antes disso.
    """
    quadros = traceback.extract_tb(rastro) if rastro else []
    nossos = [q for q in quadros if "/apps/" in q.filename.replace("\\", "/")]
    quadro = (nossos or quadros or [None])[-1]
    if quadro is None:
        return ""
    caminho = quadro.filename.replace("\\", "/")
    curto = caminho[caminho.find("apps/"):] if "apps/" in caminho else caminho.rsplit("/", 1)[-1]
    return f"{curto}:{quadro.lineno}"


def _guardar(tipo, assinatura, **dados):
    """Cria ou soma a ocorrência. Nunca levanta: registrar erro não pode
    virar outro erro na cara do cliente."""
    from .models import ErroServidor

    try:
        erro, novo = ErroServidor.objects.get_or_create(
            assinatura=assinatura,
            defaults={"tipo": tipo, **dados},
        )
        if not novo:
            erro.ocorrencias += 1
            erro.ultima_em = timezone.now()
            erro.caminho = dados.get("caminho", erro.caminho)
            erro.usuario = dados.get("usuario", erro.usuario)
            # voltou depois de marcado como resolvido: não está resolvido
            erro.resolvido = False
            erro.save(update_fields=["ocorrencias", "ultima_em", "caminho",
                                     "usuario", "resolvido"])
        return erro
    except Exception:  # noqa: BLE001 — banco fora do ar, por exemplo
        log.exception("não foi possível registrar o erro %s", tipo)
        return None


def registrar_excecao(request, exc_info) -> None:
    """Chamado pelo sinal do Django a cada exceção não tratada (erro 500)."""
    tipo_exc, excecao, rastro = exc_info
    if tipo_exc is None:
        return
    onde = _onde_estourou(rastro)
    usuario = getattr(request, "user", None) if request else None
    erro = _guardar(
        "500",
        _assinatura("500", tipo_exc.__name__, onde),
        excecao=tipo_exc.__name__,
        mensagem=str(excecao)[:2000],
        onde=onde,
        caminho=(request.get_full_path() if request else "")[:500],
        metodo=(request.method if request else "")[:10],
        usuario=(getattr(usuario, "email", "") if getattr(usuario, "is_authenticated", False) else "")[:200],
        rastro="".join(traceback.format_exception(tipo_exc, excecao, rastro))[-20000:],
    )
    if erro:
        avisar_em_segundo_plano(erro)


def registrar_linha_da_borda(linha: str):
    """Uma linha 5xx do nginx vira ocorrência. Devolve o erro ou None."""
    achado = LINHA_NGINX.match(linha.strip())
    if not achado or achado["status"] not in MOTIVO_BORDA:
        return None
    status = achado["status"]
    # agrupa por status: durante um reinício toda URL dá 502, e isso é um
    # problema só, não cinquenta
    return _guardar(
        status,
        _assinatura("borda", status),
        excecao=f"HTTP {status}",
        mensagem=MOTIVO_BORDA[status],
        onde="nginx",
        caminho=achado["caminho"][:500],
        metodo=achado["metodo"][:10],
        usuario="",
        rastro=linha.strip()[:2000],
    )


# ------------------------------------------------------------------ alerta
def destinatarios() -> list[str]:
    return [e.strip() for e in (getattr(settings, "ALERTA_ERROS_EMAIL", "") or "").split(",") if e.strip()]


def precisa_avisar(erro) -> bool:
    """Primeira vez avisa; depois, só se voltou a acontecer e já passou o
    intervalo — sem ocorrência nova não há o que contar."""
    if not destinatarios() or erro.resolvido:
        return False
    if erro.avisado_em is None:
        return True
    return (
        erro.ultima_em > erro.avisado_em
        and timezone.now() - erro.avisado_em >= INTERVALO_ALERTA
    )


def avisar(erro) -> bool:
    """Manda o e-mail do erro. Sem SMTP configurado, não marca como avisado:
    o cron tenta de novo, e o alerta sai assim que o e-mail for ligado."""
    if not precisa_avisar(erro) or not getattr(settings, "EMAIL_CONFIGURADO", False):
        return False

    site = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    assunto = f"[AgroCampo] Erro {erro.tipo}: {erro.excecao} em {erro.caminho or erro.onde}"[:200]
    corpo = (
        f"Erro {erro.tipo} no site {site or 'AgroCampo'}.\n\n"
        f"O quê: {erro.excecao} — {erro.mensagem}\n"
        f"Onde: {erro.onde}\n"
        f"Página: {erro.metodo} {erro.caminho}\n"
        f"Cliente: {erro.usuario or 'visitante'}\n"
        f"Ocorrências: {erro.ocorrencias} (primeira {erro.primeira_em:%d/%m %H:%M}, "
        f"última {erro.ultima_em:%d/%m %H:%M}, horário UTC)\n\n"
        f"Rastro:\n{erro.rastro}\n"
    )
    try:
        send_mail(assunto, corpo, None, destinatarios(), fail_silently=False)
    except Exception:  # noqa: BLE001 — SMTP recusou; o cron tenta de novo
        log.exception("alerta do erro %s não saiu", erro.pk)
        return False
    erro.avisado_em = timezone.now()
    erro.save(update_fields=["avisado_em"])
    return True


def avisar_em_segundo_plano(erro) -> None:
    """O e-mail não pode atrasar a página de erro de quem está no site."""
    if not precisa_avisar(erro) or not getattr(settings, "EMAIL_CONFIGURADO", False):
        return
    if getattr(settings, "ALERTA_ERROS_SINCRONO", False):
        avisar(erro)
        return
    threading.Thread(target=avisar, args=(erro,), daemon=True).start()
