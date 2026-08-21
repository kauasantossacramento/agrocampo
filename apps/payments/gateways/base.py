"""Contrato comum a todos os adquirentes.

Um driver traduz o vocabulário da loja (`Pagamento`) para o da API do
adquirente e devolve sempre um `ResultadoPagamento`. As views e os serviços
de pedido nunca falam com a Stone diretamente — só com esta interface.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class ErroGateway(Exception):
    """Falha de comunicação ou de negócio reportada pelo adquirente."""

    def __init__(self, mensagem, codigo="", resposta=None, http_status=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo
        self.resposta = resposta or {}
        self.http_status = http_status


@dataclass
class DadosCartao:
    """Dados transitórios do cartão. Nunca são persistidos no banco da loja."""

    numero: str
    nome: str
    validade_mes: int
    validade_ano: int
    cvv: str
    cpf_titular: str = ""

    @property
    def ultimos_digitos(self) -> str:
        return self.numero[-4:]

    @property
    def bandeira(self) -> str:
        n = self.numero.replace(" ", "")
        if n.startswith("4"):
            return "Visa"
        if n[:2] in {"51", "52", "53", "54", "55"} or n[:4] == "5067":
            return "Mastercard"
        if n[:2] in {"34", "37"}:
            return "Amex"
        if n[:6] in {"636368", "438935", "504175", "451416"}:
            return "Elo"
        if n[:4] == "6062":
            return "Hipercard"
        return "Cartão"


@dataclass
class ResultadoPagamento:
    """Resposta normalizada de qualquer operação com o adquirente."""

    sucesso: bool
    status: str
    referencia_externa: str = ""
    mensagem: str = ""
    codigo_retorno: str = ""
    codigo_autorizacao: str = ""
    nsu: str = ""
    tid: str = ""
    bandeira: str = ""
    ultimos_digitos: str = ""
    pix_qrcode: str = ""
    pix_qrcode_imagem: str = ""
    pix_expira_em: Any = None
    boleto_url: str = ""
    boleto_linha_digitavel: str = ""
    bruto: dict = field(default_factory=dict)
    http_status: int | None = None
    endpoint: str = ""
    duracao_ms: int | None = None


class GatewayBase:
    """Interface que todo adquirente precisa implementar."""

    codigo = "base"

    def __init__(self, provedor):
        self.provedor = provedor

    # ------------------------------------------------------------ helpers
    @staticmethod
    def nova_idempotency_key() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def em_centavos(valor: Decimal) -> int:
        """Stone e a maioria dos adquirentes trabalham com inteiros em centavos."""
        return int((Decimal(valor) * 100).quantize(Decimal("1")))

    def _registrar(self, pagamento, operacao, resultado, requisicao=None, erro=""):
        """Grava a trilha de auditoria da chamada."""
        from apps.payments.models import TransacaoPagamento

        return TransacaoPagamento.objects.create(
            pagamento=pagamento,
            operacao=operacao,
            sucesso=bool(resultado and resultado.sucesso),
            http_status=getattr(resultado, "http_status", None),
            endpoint=getattr(resultado, "endpoint", ""),
            requisicao=self._mascarar(requisicao or {}),
            resposta=getattr(resultado, "bruto", {}) or {},
            duracao_ms=getattr(resultado, "duracao_ms", None),
            erro=erro,
        )

    @staticmethod
    def _mascarar(dados: dict) -> dict:
        """Remove PAN, CVV e segredos antes de persistir a requisição."""
        sensiveis = {
            "number", "numero", "card_number", "cvv", "cvc", "security_code",
            "client_secret", "api_key", "authorization", "password",
        }
        limpo = {}
        for chave, valor in (dados or {}).items():
            if isinstance(valor, dict):
                limpo[chave] = GatewayBase._mascarar(valor)
            elif chave.lower() in sensiveis:
                texto = str(valor)
                limpo[chave] = f"****{texto[-4:]}" if len(texto) > 4 else "****"
            else:
                limpo[chave] = valor
        return limpo

    class _Cronometro:
        def __enter__(self):
            self.inicio = time.monotonic()
            return self

        def __exit__(self, *exc):
            self.ms = int((time.monotonic() - self.inicio) * 1000)
            return False

    # ------------------------------------------------------------ contrato
    def autorizar_cartao(self, pagamento, cartao: DadosCartao, parcelas: int = 1) -> ResultadoPagamento:
        raise NotImplementedError

    def cobrar_com_token(self, pagamento, token: str) -> ResultadoPagamento:
        """Cobrança recorrente (assinatura) com cartão previamente tokenizado."""
        raise NotImplementedError

    def tokenizar_cartao(self, usuario, cartao: DadosCartao) -> ResultadoPagamento:
        raise NotImplementedError

    def criar_pix(self, pagamento) -> ResultadoPagamento:
        raise NotImplementedError

    def criar_boleto(self, pagamento) -> ResultadoPagamento:
        raise NotImplementedError

    def capturar(self, pagamento) -> ResultadoPagamento:
        raise NotImplementedError

    def consultar(self, pagamento) -> ResultadoPagamento:
        raise NotImplementedError

    def estornar(self, pagamento, valor: Decimal) -> ResultadoPagamento:
        raise NotImplementedError

    def validar_webhook(self, corpo: bytes, assinatura: str) -> bool:
        raise NotImplementedError

    def interpretar_webhook(self, payload: dict) -> dict:
        """Normaliza o evento para `{referencia_externa, status, tipo, valor}`."""
        raise NotImplementedError
