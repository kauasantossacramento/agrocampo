"""Retoma a compressão de vídeos que ficaram pelo caminho.

A compressão roda numa thread do próprio site. Se o container reiniciar no
meio — deploy, falta de memória, queda —, o banner fica marcado como
`processando` e ninguém mais o pega. Este comando, chamado pelo cron de
minuto em minuto, devolve esses banners à fila.

Também serve para o primeiro uso depois que o ffmpeg entrou na imagem:
`python manage.py reprocessar_midia --todos` refaz tudo que ainda não tem
versão leve.
"""
from django.core.management.base import BaseCommand

from apps.core.midia import (ffmpeg_disponivel, processar_video_de,
                             processar_video_do_banner)
from apps.core.models import Banner, VideoInstagram


class Command(BaseCommand):
    help = "Comprime os vídeos de banner que ficaram sem versão leve."

    def add_arguments(self, parser):
        parser.add_argument(
            "--todos", action="store_true",
            help="Refaz também os que já falharam antes.",
        )

    def handle(self, *args, **opcoes):
        if not ffmpeg_disponivel():
            self.stderr.write("ffmpeg não está instalado — nada a fazer.")
            return

        # A condição que importa é esta: tem vídeo e não tem versão leve.
        # Olhar só o estado deixava de fora os banners que já existiam antes
        # da compressão virar regra — eles ficaram marcados como "sem vídeo"
        # e sumiram do site sem ninguém entender por quê.
        pendentes = (
            Banner.objects.exclude(video="").filter(video_otimizado="").order_by("pk")
        )
        if not opcoes["todos"]:
            # numa passada normal, quem já falhou fica de fora: o cron tentaria
            # de novo a cada minuto, de graça, para sempre
            pendentes = pendentes.exclude(video_status=Banner.Processamento.FALHOU)

        reels = (
            VideoInstagram.objects.exclude(video="").filter(video_otimizado="")
            .order_by("pk")
        )
        if not opcoes["todos"]:
            reels = reels.exclude(video_status=VideoInstagram.Processamento.FALHOU)

        for video in reels:
            self.stdout.write(f"comprimindo vídeo do Instagram {video.pk}")
            processar_video_de("core.videoinstagram", video.pk)

        for banner in pendentes:
            self.stdout.write(f"comprimindo banner {banner.pk} — {banner.titulo}")
            processar_video_do_banner(banner.pk)
            banner.refresh_from_db()
            if banner.video_status == Banner.Processamento.PRONTO:
                tamanho = banner.video_otimizado.size / 1024 / 1024
                self.stdout.write(self.style.SUCCESS(f"  pronto: {tamanho:.1f} MB"))
            else:
                self.stderr.write(f"  falhou: {banner.video_erro}")
