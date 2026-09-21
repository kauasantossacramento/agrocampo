"""Emissão de notificações. Ponto único usado por pedidos e pagamentos."""
from django.conf import settings
from django.core.mail import send_mail

from .models import Notificacao


def notificar(
    *,
    destinatario=None,
    publico=Notificacao.Publico.CLIENTE,
    tipo=Notificacao.Tipo.GERAL,
    nivel=Notificacao.Nivel.INFO,
    titulo,
    mensagem="",
    link="",
    pedido=None,
    email=False,
    whatsapp=False,
):
    """Cria a notificação in-app e, opcionalmente, dispara e-mail e WhatsApp.

    O WhatsApp só sai se o cliente autorizou contato e o envio automático
    estiver ligado no painel — e nunca derruba o fluxo se o robô cair.
    """
    notificacao = Notificacao.objects.create(
        destinatario=destinatario,
        publico=publico,
        tipo=tipo,
        nivel=nivel,
        titulo=titulo,
        mensagem=mensagem,
        link=link,
        pedido=pedido,
    )
    if email and destinatario and destinatario.email:
        try:
            send_mail(
                subject=f"[AgroCampo] {titulo}",
                message=mensagem or titulo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[destinatario.email],
                fail_silently=True,
            )
            notificacao.enviada_por_email = True
            notificacao.save(update_fields=["enviada_por_email"])
        except Exception:  # pragma: no cover - e-mail nunca derruba o fluxo
            pass
    if whatsapp and destinatario and destinatario.aceita_contato_whatsapp and destinatario.telefone:
        from . import whatsapp as canal_whatsapp

        if canal_whatsapp.ativo():
            canal_whatsapp.enviar(
                destinatario.telefone,
                canal_whatsapp.texto_da_notificacao(notificacao, destinatario.primeiro_nome),
                pedido=pedido,
                notificacao=notificacao,
            )
    return notificacao


def notificar_lojistas(*, tipo, titulo, mensagem="", link="", pedido=None, nivel=None):
    """Notificação para a equipe da loja (aparece no sino do painel)."""
    return notificar(
        destinatario=None,
        publico=Notificacao.Publico.LOJISTA,
        tipo=tipo,
        nivel=nivel or Notificacao.Nivel.INFO,
        titulo=titulo,
        mensagem=mensagem,
        link=link,
        pedido=pedido,
    )


def alertar_estoque_baixo(produto):
    """Evita spam: só alerta uma vez enquanto o estoque seguir baixo."""
    ja_alertado = Notificacao.objects.filter(
        tipo=Notificacao.Tipo.ESTOQUE_BAIXO,
        publico=Notificacao.Publico.LOJISTA,
        mensagem__startswith=produto.sku,
        lida_em__isnull=True,
    ).exists()
    if ja_alertado:
        return None
    esgotado = produto.estoque <= 0
    return notificar_lojistas(
        tipo=Notificacao.Tipo.ESTOQUE_BAIXO,
        nivel=Notificacao.Nivel.ERRO if esgotado else Notificacao.Nivel.ALERTA,
        titulo="Estoque esgotado" if esgotado else "Estoque baixo",
        mensagem=f"{produto.sku} · {produto.nome} · {produto.estoque} un",
        link="/painel/estoque/",
    )
