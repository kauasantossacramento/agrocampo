"""Lê os erros 502/503/504 anotados pelo nginx e manda os alertas pendentes.

Roda no laço do cron. O erro de gateway acontece justamente quando o
Django não responde, então só quem está fora dele — o nginx — consegue ver;
este comando, num container separado, transforma essas linhas em registro e
alerta.

O arquivo é esvaziado depois de lido. O nginx abre o log em modo de
acréscimo, então truncar não perde nada que ele escreva em seguida.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.erros import avisar, registrar_linha_da_borda
from apps.core.models import ErroServidor


class Command(BaseCommand):
    help = "Registra os 5xx do nginx e envia os alertas de erro pendentes."

    def handle(self, *args, **opcoes):
        arquivo = Path(getattr(settings, "LOG_ERROS_BORDA", "") or "/nao-existe")
        lidas = 0
        if arquivo.is_file() and arquivo.stat().st_size:
            with arquivo.open("r+", encoding="utf-8", errors="replace") as log:
                linhas = log.readlines()
                log.seek(0)
                log.truncate()
            for linha in linhas:
                if registrar_linha_da_borda(linha):
                    lidas += 1

        enviados = 0
        # erros que ainda não viraram e-mail (SMTP desligado na hora, ou
        # dentro do intervalo) — tenta agora
        for erro in ErroServidor.objects.filter(resolvido=False).order_by("-ultima_em")[:20]:
            if avisar(erro):
                enviados += 1

        if lidas or enviados:
            self.stdout.write(f"[erros] {lidas} da borda registrados, {enviados} alertas enviados")
