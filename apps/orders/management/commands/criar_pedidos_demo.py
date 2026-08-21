"""Gera pedidos em vários estágios para demonstrar o painel do lojista.

    python manage.py criar_pedidos_demo

Cria um pedido em cada ponto do fluxo: aguardando aprovação (Pix e cartão),
aprovado/em separação, enviado e recusado por falta de estoque.
"""
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.cart.models import Carrinho
from apps.catalog.models import Produto
from apps.orders.models import Pedido
from apps.orders.services import (
    aprovar_pedido,
    criar_pedido_do_carrinho,
    marcar_enviado,
    recusar_pedido,
)
from apps.payments.services import cobrar_cartao, cobrar_pix

User = get_user_model()

CARTAO = {
    "numero": "4111111111111234",
    "nome": "MARIA SILVA",
    "validade_mes": 12,
    "validade_ano": 2030,
    "cvv": "123",
}


class Command(BaseCommand):
    help = "Cria pedidos de demonstração em diferentes estágios do fluxo."

    def handle(self, *args, **opcoes):
        cliente = User.objects.filter(email="cliente@agrocampo.com.br").first()
        lojista = User.objects.filter(email="lojista@agrocampo.com.br").first()
        if not (cliente and lojista):
            raise CommandError("Rode antes: python manage.py criar_usuarios_demo")

        produtos = list(Produto.objects.filter(publicado=True, estoque__gt=3))
        if len(produtos) < 4:
            raise CommandError("Rode antes: python manage.py seed")

        random.seed(42)  # cenário reproduzível

        # 1) aguardando aprovação, pago via Pix
        pedido = self._pedido(cliente, random.sample(produtos, 2))
        pagamento = cobrar_pix(pedido)
        pagamento.marcar_pago(pagamento.referencia_externa, "Pix confirmado (demo).")
        from apps.payments.services import _confirmar_pedido

        _confirmar_pedido(pedido, pagamento)
        self.stdout.write(f"  {pedido.numero} · aguardando aprovação (Pix)")

        # 2) aguardando aprovação, pago no cartão
        pedido = self._pedido(cliente, random.sample(produtos, 1))
        cobrar_cartao(pedido, CARTAO, parcelas=3)
        self.stdout.write(f"  {pedido.numero} · aguardando aprovação (cartão 3x)")

        # 3) aprovado e em separação
        pedido = self._pedido(cliente, random.sample(produtos, 2))
        cobrar_cartao(pedido, CARTAO)
        aprovar_pedido(pedido, lojista)
        self.stdout.write(f"  {pedido.numero} · em separação")

        # 4) enviado
        pedido = self._pedido(cliente, random.sample(produtos, 1))
        cobrar_cartao(pedido, CARTAO)
        aprovar_pedido(pedido, lojista)
        marcar_enviado(pedido, lojista, "BR123456789AG")
        self.stdout.write(f"  {pedido.numero} · enviado")

        # 5) recusado por falta de estoque (habilita sugestões + estorno)
        pedido = self._pedido(cliente, random.sample(produtos, 1))
        cobrar_cartao(pedido, CARTAO)
        recusar_pedido(pedido, lojista, "Produto sem estoque no momento da conferência")
        self.stdout.write(f"  {pedido.numero} · recusado (com opção de estorno)")

        self.stdout.write(self.style.SUCCESS("\nPedidos de demonstração criados."))
        self.stdout.write("Painel: http://127.0.0.1:8000/painel/")

    def _pedido(self, cliente, produtos) -> Pedido:
        carrinho = Carrinho.objects.create(usuario=cliente)
        for produto in produtos:
            recorrente = produto.permite_assinatura and random.random() < 0.4
            carrinho.adicionar(produto, 1, recorrente, 30 if recorrente else None)
        pedido = criar_pedido_do_carrinho(carrinho, cliente)
        carrinho.finalizado = True
        carrinho.save(update_fields=["finalizado"])
        return pedido
