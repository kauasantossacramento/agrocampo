"""Compressão de mídia dos banners.

O lojista filma no celular e manda o arquivo como saiu da câmera — meio
minuto em 4K dá 226 MB. Mandar ele "comprimir e tentar de novo" é empurrar
para o balcão um trabalho que o servidor faz em segundos, então a loja aceita
o arquivo grande e gera sozinha a versão leve. **É a versão leve que vai ao
ar**; o original fica guardado, caso um dia seja preciso refazer.

O trabalho roda numa thread para a requisição não ficar presa: o lojista vê
"processando vídeo…" na listagem e continua trabalhando. Se o container cair
no meio, o banner fica marcado como `processando` e o comando
`reprocessar_midia` (rodado pelo cron) retoma de onde parou.

Sem o ffmpeg instalado nada quebra: o banner fica marcado como falho, com o
motivo, e o lojista vê o aviso no painel.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile

log = logging.getLogger(__name__)

# 1920 de largura cobre qualquer tela que a loja vá encontrar; CRF 27 é o
# ponto em que o vídeo de banner ainda fica limpo e o arquivo cai para alguns
# megabytes. Sem áudio de propósito: o banner toca mudo de qualquer jeito.
LARGURA_MAXIMA = 1920
QUALIDADE = "27"
TEMPO_LIMITE = 60 * 25          # 25 min: vídeo longo em servidor ocupado


def ffmpeg_disponivel() -> str | None:
    return shutil.which("ffmpeg")


def _rodar(comando: list[str]) -> None:
    resultado = subprocess.run(
        comando, capture_output=True, text=True, timeout=TEMPO_LIMITE,
    )
    if resultado.returncode != 0:
        # a última linha do ffmpeg é a que diz o motivo; o resto é cabeçalho
        erro = (resultado.stderr or "").strip().splitlines()
        raise RuntimeError(erro[-1] if erro else "ffmpeg falhou sem explicar")


def comprimir_video(origem: Path, destino: Path) -> None:
    """H.264 em MP4, pronto para começar a tocar antes de baixar inteiro."""
    _rodar([
        "ffmpeg", "-y", "-i", str(origem),
        "-vf", f"scale='min({LARGURA_MAXIMA},iw)':-2",
        "-c:v", "libx264", "-preset", "medium", "-crf", QUALIDADE,
        "-pix_fmt", "yuv420p",
        # faststart põe o índice no começo: o vídeo começa a tocar enquanto
        # o resto ainda chega, que é o que importa no 4G
        "-movflags", "+faststart",
        "-an",                       # banner toca mudo
        str(destino),
    ])


def extrair_capa(origem: Path, destino: Path) -> None:
    """Um quadro do primeiro segundo, para a tela não ficar preta carregando."""
    _rodar([
        "ffmpeg", "-y", "-ss", "00:00:01", "-i", str(origem),
        "-frames:v", "1", "-vf", f"scale='min({LARGURA_MAXIMA},iw)':-2",
        "-q:v", "3", str(destino),
    ])


LARGURA_IMAGEM = 2000


def otimizar_imagem(campo, destino_nome: str):
    """Devolve (nome, conteúdo) de uma versão WebP reduzida — ou None.

    O original continua intocado no campo de sempre: se um dia a loja trocar
    de tema ou precisar reexportar, é dele que se parte.
    """
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError:          # Pillow é dependência do projeto; se faltar, segue
        return None

    try:
        with campo.open("rb") as arquivo:
            imagem = Image.open(arquivo)
            imagem.load()
    except Exception as exc:     # noqa: BLE001
        log.warning("não consegui abrir %s: %s", destino_nome, exc)
        return None

    if imagem.mode in ("RGBA", "LA", "P"):
        imagem = imagem.convert("RGBA")
    else:
        imagem = imagem.convert("RGB")

    if imagem.width > LARGURA_IMAGEM:
        altura = round(imagem.height * LARGURA_IMAGEM / imagem.width)
        imagem = imagem.resize((LARGURA_IMAGEM, altura), Image.LANCZOS)

    buffer = BytesIO()
    imagem.save(buffer, format="WEBP", quality=82, method=4)
    return destino_nome, ContentFile(buffer.getvalue())


def processar_imagens_do_banner(banner_id: int) -> None:
    """Gera as versões WebP das artes do banner, sem tocar nos originais."""
    from apps.core.models import Banner

    banner = Banner.objects.filter(pk=banner_id).first()
    if not banner:
        return

    mudou = []
    for campo, alvo in (("imagem", "imagem_web"), ("imagem_movel", "imagem_movel_web")):
        arquivo = getattr(banner, campo)
        if not arquivo:
            continue
        feito = otimizar_imagem(arquivo, f"{Path(arquivo.name).stem}.webp")
        if not feito:
            continue
        nome, conteudo = feito
        getattr(banner, alvo).save(nome, conteudo, save=False)
        mudou.append(alvo)

    if mudou:
        banner.save(update_fields=mudou + ["atualizado_em"])


def processar_video_do_banner(banner_id: int) -> None:
    """Gera versão leve e capa de um banner. Guarda o motivo quando falha."""
    from apps.core.models import Banner

    banner = Banner.objects.filter(pk=banner_id).first()
    if not banner or not banner.video:
        return

    if not ffmpeg_disponivel():
        Banner.objects.filter(pk=banner_id).update(
            video_status=Banner.Processamento.FALHOU,
            video_erro="ffmpeg não está instalado neste servidor.",
        )
        return

    Banner.objects.filter(pk=banner_id).update(
        video_status=Banner.Processamento.PROCESSANDO, video_erro="",
    )

    try:
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / Path(banner.video.name).name
            # o arquivo pode estar em qualquer storage: copiamos para o disco
            with banner.video.open("rb") as origem, open(entrada, "wb") as copia:
                shutil.copyfileobj(origem, copia)

            leve = pasta / "leve.mp4"
            capa = pasta / "capa.jpg"
            comprimir_video(entrada, leve)
            try:
                extrair_capa(entrada, capa)
            except Exception as exc:          # noqa: BLE001
                # sem capa o vídeo ainda toca; não vale derrubar o processo
                log.warning("capa do banner %s falhou: %s", banner_id, exc)
                capa = None

            base = Path(banner.video.name).stem
            with open(leve, "rb") as arquivo:
                banner.video_otimizado.save(f"{base}.mp4", File(arquivo), save=False)
            if capa and capa.exists():
                with open(capa, "rb") as arquivo:
                    banner.video_poster.save(f"{base}.jpg", File(arquivo), save=False)

        banner.video_status = Banner.Processamento.PRONTO
        banner.video_erro = ""
        banner.save(update_fields=[
            "video_otimizado", "video_poster", "video_status", "video_erro",
            "atualizado_em",
        ])
        log.info("banner %s: vídeo comprimido", banner_id)
    except Exception as exc:                   # noqa: BLE001
        log.exception("banner %s: falha ao comprimir", banner_id)
        Banner.objects.filter(pk=banner_id).update(
            video_status=Banner.Processamento.FALHOU,
            video_erro=str(exc)[:300],
        )


def processar_video_de(modelo_rotulo: str, objeto_id: int) -> None:
    """Mesma compressão dos banners, para qualquer objeto que tenha os campos
    `video`, `video_otimizado`, `video_poster`, `video_status` e `video_erro`.

    É o caso dos vídeos do Instagram: a regra de negócio é a mesma — o que vai
    ao ar é a versão leve — e duplicar o pipeline só criaria dois lugares para
    consertar quando o ffmpeg mudar de opinião.
    """
    from django.apps import apps as registro

    Modelo = registro.get_model(*modelo_rotulo.split("."))
    objeto = Modelo.objects.filter(pk=objeto_id).first()
    if not objeto or not objeto.video:
        return

    estados = Modelo.Processamento
    if not ffmpeg_disponivel():
        Modelo.objects.filter(pk=objeto_id).update(
            video_status=estados.FALHOU,
            video_erro="ffmpeg não está instalado neste servidor.",
        )
        return

    Modelo.objects.filter(pk=objeto_id).update(
        video_status=estados.PROCESSANDO, video_erro="",
    )

    try:
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            entrada = pasta / Path(objeto.video.name).name
            with objeto.video.open("rb") as origem, open(entrada, "wb") as copia:
                shutil.copyfileobj(origem, copia)

            leve = pasta / "leve.mp4"
            capa = pasta / "capa.jpg"
            comprimir_video(entrada, leve)
            try:
                extrair_capa(entrada, capa)
            except Exception as exc:          # noqa: BLE001
                log.warning("capa de %s %s falhou: %s", modelo_rotulo, objeto_id, exc)
                capa = None

            base = Path(objeto.video.name).stem
            with open(leve, "rb") as arquivo:
                objeto.video_otimizado.save(f"{base}.mp4", File(arquivo), save=False)
            if capa and capa.exists():
                with open(capa, "rb") as arquivo:
                    objeto.video_poster.save(f"{base}.jpg", File(arquivo), save=False)

        objeto.video_status = estados.PRONTO
        objeto.video_erro = ""
        # `save()` do modelo reagendaria o trabalho; aqui grava direto
        Modelo.objects.filter(pk=objeto_id).update(
            video_otimizado=objeto.video_otimizado.name,
            video_poster=objeto.video_poster.name if objeto.video_poster else "",
            video_status=estados.PRONTO,
            video_erro="",
        )
        log.info("%s %s: vídeo comprimido", modelo_rotulo, objeto_id)
    except Exception as exc:                   # noqa: BLE001
        log.exception("%s %s: falha ao comprimir", modelo_rotulo, objeto_id)
        Modelo.objects.filter(pk=objeto_id).update(
            video_status=estados.FALHOU, video_erro=str(exc)[:300],
        )


def agendar_video(objeto) -> None:
    """Põe o vídeo de qualquer objeto na fila, sem segurar a requisição."""
    rotulo = f"{objeto._meta.app_label}.{objeto._meta.model_name}"
    threading.Thread(
        target=processar_video_de, args=(rotulo, objeto.pk),
        daemon=True, name=f"video-{rotulo}-{objeto.pk}",
    ).start()


def agendar_processamento(banner_id: int, com_video: bool = True) -> None:
    """Põe a mídia na fila e devolve a requisição na hora.

    Thread em vez de fila de tarefas porque a loja tem um container só e um
    vídeo por vez; trazer Celery e Redis para isso seria mais peça para
    quebrar do que trabalho economizado. O que protege contra o container
    cair no meio é o comando `reprocessar_midia`, no cron.
    """
    from apps.core.models import Banner

    def trabalho():
        processar_imagens_do_banner(banner_id)
        if com_video:
            processar_video_do_banner(banner_id)

    if com_video:
        Banner.objects.filter(pk=banner_id).update(
            video_status=Banner.Processamento.NA_FILA, video_erro="",
        )
    threading.Thread(
        target=trabalho, daemon=True, name=f"midia-banner-{banner_id}",
    ).start()
