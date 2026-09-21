"""Fecha a etapa de aprovação: pedidos parados nos status legados seguem o fluxo atual.

A aprovação deixou de existir em 22/08/2026 (pago vai direto para separação),
mas pedidos feitos antes disso continuaram parados em "aguardando aprovação" e
"aprovado" — e eram eles que faziam o painel ainda mostrar botões de aprovar.
Aqui eles passam para "em separação", com um evento na timeline explicando.
Estoque não é mexido: esses pedidos já foram tratados à mão na época.
"""
from django.db import migrations


def liberar_legados(apps, schema_editor):
    Pedido = apps.get_model("orders", "Pedido")
    EventoPedido = apps.get_model("orders", "EventoPedido")
    legados = Pedido.objects.filter(status__in=["aguardando_aprovacao", "aprovado"])
    for pedido in legados:
        anterior = pedido.status
        pedido.status = "em_separacao"
        pedido.save(update_fields=["status"])
        EventoPedido.objects.create(
            pedido=pedido,
            status_anterior=anterior,
            status_novo="em_separacao",
            titulo="Em separação",
            descricao="A etapa de aprovação foi removida da loja; o pedido seguiu o fluxo atual.",
        )


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_itempedido_variacao_itempedido_variacao_rotulo_and_more")]
    operations = [migrations.RunPython(liberar_legados, migrations.RunPython.noop)]
