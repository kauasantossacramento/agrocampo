"""Canal de WhatsApp automático, via serviço `whatsapp` (whatsapp-web.js).

Aviso honesto, repetido aqui porque é onde alguém vai mexer: esse canal usa
uma sessão do WhatsApp Web controlada por robô. Não é a API oficial da Meta
e viola os Termos de Serviço do WhatsApp — o número da loja pode ser banido.
O lojista decidiu usar assim mesmo; por isso há um interruptor no painel e o
link wa.me continua existindo como caminho manual.

O Django nunca fala com o WhatsApp diretamente: fala com o serviço Node
(`deploy/whatsapp/`), que expõe três rotas protegidas por token:
GET /status, POST /enviar e POST /desconectar.
"""
import logging

import requests
from django.conf import settings

from .models import MensagemWhatsApp

log = logging.getLogger(__name__)

TIMEOUT = 8  # segundos — o checkout não pode ficar preso esperando o robô


def configurado() -> bool:
    return bool(settings.WHATSAPP_WEB_URL and settings.WHATSAPP_WEB_TOKEN)


def ativo() -> bool:
    """Ligado no painel *e* com o serviço configurado no ambiente."""
    from apps.core.models import SiteConfig

    return configurado() and SiteConfig.load().whatsapp_auto_ativo


def normalizar_numero(telefone: str) -> str:
    """'(75) 99999-0000' vira '5575999990000'. Vazio se não parecer telefone."""
    digitos = "".join(c for c in (telefone or "") if c.isdigit())
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return digitos
    if len(digitos) in (10, 11):
        return "55" + digitos
    return ""


def _cabecalhos():
    return {"Authorization": f"Bearer {settings.WHATSAPP_WEB_TOKEN}"}


def status_sessao() -> dict:
    """Estado da sessão para o painel: conectado, QR pendente, desligado."""
    if not configurado():
        return {
            "estado": "nao_configurado", "qr": None, "numero": "",
            "detalhe": "Entre em contato com o suporte KS TEC para ativar a funcionalidade.",
        }
    try:
        resposta = requests.get(
            f"{settings.WHATSAPP_WEB_URL}/status", headers=_cabecalhos(), timeout=TIMEOUT
        )
        resposta.raise_for_status()
        dados = resposta.json()
        return {
            "estado": dados.get("estado", "desconhecido"),
            "qr": dados.get("qr"),
            "detalhe": dados.get("detalhe", ""),
            "numero": dados.get("numero", ""),
        }
    except (requests.RequestException, ValueError) as exc:
        return {"estado": "indisponivel", "qr": None, "numero": "", "detalhe": str(exc)[:200]}


def desconectar() -> bool:
    if not configurado():
        return False
    try:
        resposta = requests.post(
            f"{settings.WHATSAPP_WEB_URL}/desconectar", headers=_cabecalhos(), timeout=TIMEOUT
        )
        return resposta.ok
    except requests.RequestException:
        return False


def enviar(numero: str, texto: str, *, pedido=None, notificacao=None,
           ignorar_interruptor=False) -> MensagemWhatsApp:
    """Envia uma mensagem e registra o resultado. Nunca levanta exceção.

    `ignorar_interruptor` serve para o botão "enviar teste" do painel, que
    precisa funcionar antes de o lojista ligar o envio automático.
    """
    numero_limpo = normalizar_numero(numero)
    registro = MensagemWhatsApp(
        notificacao=notificacao, pedido=pedido, numero=numero_limpo or numero, texto=texto
    )

    if not numero_limpo:
        registro.status = MensagemWhatsApp.Status.IGNORADA
        registro.erro = "Número inválido."
    elif not configurado():
        registro.status = MensagemWhatsApp.Status.IGNORADA
        registro.erro = "Serviço não ativado — fale com o suporte KS TEC."
    elif not ignorar_interruptor and not ativo():
        registro.status = MensagemWhatsApp.Status.IGNORADA
        registro.erro = "Envio automático desligado no painel."
    else:
        try:
            resposta = requests.post(
                f"{settings.WHATSAPP_WEB_URL}/enviar",
                json={"numero": numero_limpo, "texto": texto},
                headers=_cabecalhos(),
                timeout=TIMEOUT,
            )
            if resposta.ok:
                registro.status = MensagemWhatsApp.Status.ENVIADA
            else:
                registro.status = MensagemWhatsApp.Status.FALHOU
                try:
                    registro.erro = (resposta.json().get("erro") or resposta.text)[:300]
                except ValueError:
                    registro.erro = resposta.text[:300]
        except requests.RequestException as exc:
            registro.status = MensagemWhatsApp.Status.FALHOU
            registro.erro = str(exc)[:300]
            log.warning("WhatsApp indisponível: %s", exc)

    registro.save()
    if notificacao and registro.status == MensagemWhatsApp.Status.ENVIADA:
        notificacao.enviada_por_whatsapp = True
        notificacao.save(update_fields=["enviada_por_whatsapp"])
    return registro


def texto_da_notificacao(notificacao, nome: str = "") -> str:
    """Monta o texto do aviso a partir da notificação in-app."""
    partes = []
    if nome:
        partes.append(f"Olá, {nome}!")
    partes.append(f"*{notificacao.titulo}*")
    if notificacao.mensagem:
        partes.append(notificacao.mensagem)
    if notificacao.link and settings.SITE_URL:
        link = notificacao.link
        if link.startswith("/"):
            link = settings.SITE_URL + link
        partes.append(link)
    return "\n".join(partes)
