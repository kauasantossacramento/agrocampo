"""Driver simulado — permite rodar o checkout completo sem a Stone plugada.

Ele imita o comportamento do adquirente de forma determinística, para que o
fluxo de pedido, aprovação do lojista, assinatura e estorno possa ser
desenvolvido e testado ponta a ponta. Regras de simulação:

- cartão terminado em `0000` → recusado;
- cartão terminado em `1111` → autorizado, mas não capturado;
- qualquer outro → aprovado;
- Pix → gera um BR Code válido em formato, confirmado pela rota de
  simulação `/pagamentos/simular-pix/<id>/`.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .base import DadosCartao, GatewayBase, ResultadoPagamento
from .stone import MAPA_STATUS


def _crc16(payload: str) -> str:
    """CRC-16/CCITT-FALSE — exigido pelo padrão BR Code do Pix."""
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _campo(identificador: str, valor: str) -> str:
    return f"{identificador}{len(valor):02d}{valor}"


def montar_brcode(chave: str, valor: Decimal, nome: str, cidade: str, txid: str) -> str:
    """Monta um payload Pix estático conforme o manual do BACEN."""
    merchant = _campo("00", "br.gov.bcb.pix") + _campo("01", chave or "agrocampo@pix.com.br")
    payload = (
        _campo("00", "01")
        + _campo("26", merchant)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("54", f"{Decimal(valor):.2f}")
        + _campo("58", "BR")
        + _campo("59", (nome or "AGROCAMPO")[:25].upper())
        + _campo("60", (cidade or "SAO PAULO")[:15].upper())
        + _campo("62", _campo("05", txid[:25]))
        + "6304"
    )
    return payload + _crc16(payload)


class SimuladoGateway(GatewayBase):
    codigo = "simulado"

    def _ref(self, prefixo="sim"):
        return f"{prefixo}_{uuid.uuid4().hex[:20]}"

    def autorizar_cartao(self, pagamento, cartao: DadosCartao, parcelas=1):
        ultimos = cartao.ultimos_digitos
        if ultimos == "0000":
            resultado = ResultadoPagamento(
                sucesso=False,
                status="recusado",
                mensagem="Cartão recusado pelo emissor (simulação).",
                codigo_retorno="51",
                bandeira=cartao.bandeira,
                ultimos_digitos=ultimos,
                bruto={"simulado": True, "status": "declined"},
            )
        else:
            capturado = self.provedor.captura_automatica and ultimos != "1111"
            resultado = ResultadoPagamento(
                sucesso=True,
                status="pago" if capturado else "autorizado",
                referencia_externa=self._ref("chg"),
                mensagem="Transação aprovada (simulação).",
                codigo_autorizacao=uuid.uuid4().hex[:6].upper(),
                nsu=uuid.uuid4().int % 1000000,
                tid=self._ref("tid"),
                bandeira=cartao.bandeira,
                ultimos_digitos=ultimos,
                bruto={"simulado": True, "status": "paid" if capturado else "authorized"},
            )
            resultado.nsu = str(resultado.nsu)
        resultado.endpoint = "simulado://charges"
        resultado.duracao_ms = 40
        self._registrar(
            pagamento,
            "autorizacao",
            resultado,
            {"amount": self.em_centavos(pagamento.valor), "installments": parcelas},
        )
        return resultado

    def cobrar_com_token(self, pagamento, token: str):
        resultado = ResultadoPagamento(
            sucesso=True,
            status="pago",
            referencia_externa=self._ref("rec"),
            mensagem="Cobrança recorrente aprovada (simulação).",
            codigo_autorizacao=uuid.uuid4().hex[:6].upper(),
            bruto={"simulado": True, "status": "paid", "card_id": token},
            endpoint="simulado://charges",
            duracao_ms=35,
        )
        self._registrar(pagamento, "recorrencia", resultado, {"card_id": token})
        return resultado

    def tokenizar_cartao(self, usuario, cartao: DadosCartao):
        return ResultadoPagamento(
            sucesso=True,
            status="pago",
            referencia_externa=self._ref("card"),
            bandeira=cartao.bandeira,
            ultimos_digitos=cartao.ultimos_digitos,
            mensagem="Cartão tokenizado (simulação).",
            bruto={"simulado": True},
        )

    def criar_pix(self, pagamento):
        pedido = pagamento.pedido
        endereco = pedido.endereco_entrega
        brcode = montar_brcode(
            self.provedor.stone_pix_chave,
            pagamento.valor,
            "AGROCAMPO",
            endereco.cidade if endereco else "SAO PAULO",
            pedido.numero.replace("-", ""),
        )
        resultado = ResultadoPagamento(
            sucesso=True,
            status="pendente",
            referencia_externa=self._ref("pix"),
            pix_qrcode=brcode,
            pix_expira_em=timezone.now()
            + timedelta(minutes=self.provedor.pix_expira_em_minutos),
            mensagem="QR Code gerado (simulação).",
            bruto={"simulado": True, "status": "pending"},
            endpoint="simulado://pix/charges",
            duracao_ms=25,
        )
        self._registrar(pagamento, "autorizacao", resultado, {"amount": str(pagamento.valor)})
        return resultado

    def criar_boleto(self, pagamento):
        resultado = ResultadoPagamento(
            sucesso=True,
            status="pendente",
            referencia_externa=self._ref("bol"),
            boleto_linha_digitavel="34191.79001 01043.510047 91020.150008 5 91230000019990",
            boleto_url="",
            mensagem="Boleto gerado (simulação).",
            bruto={"simulado": True, "status": "pending"},
        )
        self._registrar(pagamento, "autorizacao", resultado, {})
        return resultado

    def capturar(self, pagamento):
        resultado = ResultadoPagamento(
            sucesso=True,
            status="pago",
            referencia_externa=pagamento.referencia_externa,
            mensagem="Captura confirmada (simulação).",
            bruto={"simulado": True, "status": "paid"},
        )
        self._registrar(pagamento, "captura", resultado, {})
        return resultado

    def consultar(self, pagamento):
        resultado = ResultadoPagamento(
            sucesso=True,
            status=pagamento.status,
            referencia_externa=pagamento.referencia_externa,
            bruto={"simulado": True, "status": pagamento.status},
        )
        self._registrar(pagamento, "consulta", resultado)
        return resultado

    def estornar(self, pagamento, valor: Decimal):
        resultado = ResultadoPagamento(
            sucesso=True,
            status="estornado",
            referencia_externa=self._ref("ref"),
            mensagem=f"Estorno de R$ {valor} processado (simulação).",
            bruto={"simulado": True, "status": "refunded", "amount": str(valor)},
        )
        self._registrar(pagamento, "estorno", resultado, {"amount": str(valor)})
        return resultado

    def validar_webhook(self, corpo: bytes, assinatura: str) -> bool:
        segredo = self.provedor.stone_webhook_secret
        if not segredo:
            return True  # ambiente de simulação sem segredo configurado
        esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperado, (assinatura or "").split("=")[-1].strip())

    def interpretar_webhook(self, payload: dict) -> dict:
        """Traduz o evento usando o mesmo mapa da Stone.

        Sem isso, um payload com `status: "paid"` chegaria cru ao model e
        nunca casaria com `Pagamento.Status.PAGO`.
        """
        dados = payload.get("data", payload)
        status_bruto = str(dados.get("status", "")).lower()
        return {
            "tipo": payload.get("type", ""),
            "referencia_externa": str(dados.get("id", "")),
            "status": MAPA_STATUS.get(status_bruto, status_bruto),
            "valor": Decimal(str(dados["amount"])) / 100 if dados.get("amount") else None,
            "e2e_id": dados.get("end_to_end_id", ""),
        }
