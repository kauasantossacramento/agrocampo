"""Busca automática dos vídeos do Instagram (Graph API).

É o caminho **opcional** do item 5: com um token de longa duração e o ID da
conta comercial, a loja traz os reels sozinha. Sem isso, valem os vídeos
cadastrados à mão no painel — e é assim que a seção funciona hoje.

Por que não é o caminho padrão: a Graph API exige conta Business ou Creator
ligada a uma Página do Facebook, um app revisado pela Meta e um token que
expira a cada 60 dias. Enquanto a loja não tiver isso, o cadastro manual
entrega o mesmo resultado para quem visita o site.

Stories somem do Instagram em 24 h. Esta função traz as mídias recentes
(reels e vídeos do feed); o que a loja quiser guardar para sempre deve ser
subido no cadastro manual.
"""
from __future__ import annotations

import logging

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)

BASE = "https://graph.facebook.com/v21.0"
CHAVE_CACHE = "instagram:midias"
VALIDADE = 45 * 60          # 45 min: a Meta limita chamadas por hora
TEMPO_LIMITE = 10


def buscar_midias(config, limite: int = 12) -> list[dict]:
    """Devolve os vídeos recentes da conta, ou lista vazia se não der.

    Nunca levanta exceção: a home não pode quebrar porque o token venceu.
    """
    if not (config.instagram_token and config.instagram_conta_id):
        return []

    guardado = cache.get(CHAVE_CACHE)
    if guardado is not None:
        return guardado

    campos = "id,media_type,media_url,permalink,thumbnail_url,caption,timestamp"
    try:
        resposta = requests.get(
            f"{BASE}/{config.instagram_conta_id}/media",
            params={
                "fields": campos,
                "limit": limite * 2,      # sobra para filtrar só o que é vídeo
                "access_token": config.instagram_token,
            },
            timeout=TEMPO_LIMITE,
        )
        dados = resposta.json()
    except Exception as exc:               # noqa: BLE001
        log.warning("Instagram indisponível: %s", exc)
        cache.set(CHAVE_CACHE, [], 5 * 60)   # não insiste a cada visita
        return []

    if "error" in dados:
        # token vencido é o caso comum: avisa no log e segue com o manual
        log.warning("Instagram recusou: %s", dados["error"].get("message"))
        cache.set(CHAVE_CACHE, [], 5 * 60)
        return []

    videos = [
        {
            "id": item.get("id"),
            "video": item.get("media_url"),
            "capa": item.get("thumbnail_url"),
            "link": item.get("permalink"),
            "legenda": (item.get("caption") or "")[:220],
        }
        for item in dados.get("data", [])
        if item.get("media_type") in ("VIDEO", "REELS") and item.get("media_url")
    ][:limite]

    cache.set(CHAVE_CACHE, videos, VALIDADE)
    return videos


def limpar_cache() -> None:
    """Usado pelo painel depois de trocar o token."""
    cache.delete(CHAVE_CACHE)
