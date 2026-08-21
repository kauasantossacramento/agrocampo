"""Processa os ciclos de assinatura vencidos.

Agende diariamente:
    python manage.py processar_assinaturas
"""
from django.core.management.base import BaseCommand

from apps.subscriptions.services import processar_vencidas


class Command(BaseCommand):
    help = "Cobra e gera os pedidos das assinaturas com entrega vencida."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Apenas lista o que seria processado, sem cobrar.",
        )

    def handle(self, *args, **opcoes):
        if opcoes["dry_run"]:
            from django.utils import timezone

            from apps.subscriptions.models import Assinatura

            vencidas = Assinatura.objects.filter(
                status__in=[Assinatura.Status.ATIVA, Assinatura.Status.INADIMPLENTE],
                proxima_entrega__lte=timezone.localdate(),
            )
            for a in vencidas:
                self.stdout.write(f"  {a.usuario.email} · {a.produto.nome} · {a.proxima_entrega}")
            self.stdout.write(self.style.WARNING(f"{vencidas.count()} assinatura(s) vencida(s)."))
            return

        ciclos = processar_vencidas()
        pagos = sum(1 for c in ciclos if c.status == "pago")
        falhas = len(ciclos) - pagos
        self.stdout.write(
            self.style.SUCCESS(f"{len(ciclos)} ciclo(s) processado(s): {pagos} pago(s), {falhas} falha(s).")
        )
