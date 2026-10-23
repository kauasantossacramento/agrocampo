"""Driver da Cielo — API e-Commerce 3.0.

A loja pode operar com a Stone/Pagar.me ou com a Cielo; quem decide é o
lojista, em Configurações › Pagamentos, trocando o *driver*. O resto do
sistema não sabe a diferença: fala com `GatewayBase` e recebe
`ResultadoPagamento`.

Três coisas separam a Cielo da Stone e explicam o formato deste arquivo:

* **Autenticação sem OAuth.** Não há token a renovar: `MerchantId` e
  `MerchantKey` vão no cabeçalho de toda requisição.
* **Dois endereços.** Um host recebe o que mexe em dinheiro (autorizar,
  capturar, cancelar) e outro só responde consulta. Mandar consulta para o
  host transacional é erro de rota, não de credencial.
* **Valores em centavos e status numérico.** 0 NotFinished, 1 Authorized,
  2 PaymentConfirmed, 3 Declined, 10 Voided, 11 Refunded, 12 Pending,
  13 Aborted, 20 Scheduled.

Referência: https://docs.cielo.com.br/ecommerce-cielo/v3.0-en/reference/
"""
from __future__ import annotations

import json
from decimal import Decimal

import requests

from .base import DadosCartao, ErroGateway, GatewayBase, ResultadoPagamento

# Caminhos da API. Mudança de contrato se resolve aqui, num lugar só.
ENDPOINTS = {
    "vendas": "/1/sales/",
    "venda": "/1/sales/{id}",
    "capturar": "/1/sales/{id}/capture",
    "cancelar": "/1/sales/{id}/void",
    "cartao_salvo": "/1/card/",
}

# status numérico da Cielo -> status do model Pagamento
MAPA_STATUS = {
    0: "processando",      # NotFinished
    1: "autorizado",       # Authorized — dá para capturar
    2: "pago",             # PaymentConfirmed
    3: "recusado",         # Declined
    10: "cancelado",       # Voided
    11: "estornado",       # Refunded
    12: "processando",     # Pending — esperando o banco
    13: "cancelado",       # Aborted — falha ou antifraude
    20: "processando",     # Scheduled — recorrência agendada
}


class CieloGateway(GatewayBase):
    codigo = "cielo"

    # ------------------------------------------------------------- infra
    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "MerchantId": self.provedor.cielo_merchant_id,
            "MerchantKey": self.provedor.cielo_merchant_key,
            "User-Agent": "AgroCampo/1.0",
        }

    def _chamar(self, metodo, caminho, payload=None, consulta=False):
        """Uma chamada à Cielo, no host certo, com o tempo medido.

        `consulta=True` manda para o host de leitura — a Cielo recusa
        consulta no host transacional.
        """
        base = (
            self.provedor.cielo_url_consulta if consulta else self.provedor.cielo_url
        ).rstrip("/")
        url = f"{base}{caminho}"

        with self._Cronometro() as crono:
            try:
                resposta = requests.request(
                    metodo,
                    url,
                    headers=self._headers(),
                    data=json.dumps(payload) if payload is not None else None,
                    timeout=self.provedor.timeout_segundos,
                )
            except requests.RequestException as exc:
                raise ErroGateway(f"Falha de comunicação com a Cielo: {exc}") from exc

        return resposta.status_code, self._json(resposta), crono.ms, url

    @staticmethod
    def _json(resposta):
        try:
            return resposta.json()
        except ValueError:
            return {"raw": resposta.text[:2000]}

    # --------------------------------------------------------- traduções
    @staticmethod
    def _erros(corpo) -> str:
        """A Cielo devolve erro como lista de objetos, não como texto."""
        if isinstance(corpo, list):
            partes = [
                f"{item.get('Code', '')} {item.get('Message', '')}".strip()
                for item in corpo
            ]
            return " · ".join(p for p in partes if p)
        if isinstance(corpo, dict) and corpo.get("Message"):
            return str(corpo["Message"])
        return ""

    def _resultado(self, http_status, corpo, ms, url) -> ResultadoPagamento:
        pagamento = (corpo or {}).get("Payment", {}) if isinstance(corpo, dict) else {}
        status_cielo = pagamento.get("Status")
        status = MAPA_STATUS.get(status_cielo, "processando")

        erro = self._erros(corpo)
        sucesso = http_status < 400 and status not in {"recusado", "cancelado"}
        if erro and http_status >= 400:
            sucesso = False

        cartao = pagamento.get("CreditCard") or pagamento.get("DebitCard") or {}
        return ResultadoPagamento(
            sucesso=sucesso,
            status=status,
            referencia_externa=str(pagamento.get("PaymentId", "")),
            mensagem=erro or pagamento.get("ReturnMessage", ""),
            codigo_retorno=str(pagamento.get("ReturnCode", "")),
            codigo_autorizacao=str(pagamento.get("AuthorizationCode", "")),
            nsu=str(pagamento.get("ProofOfSale", "")),
            tid=str(pagamento.get("Tid", "")),
            bandeira=cartao.get("Brand", ""),
            ultimos_digitos=(cartao.get("CardNumber", "") or "")[-4:],
            pix_qrcode=pagamento.get("QrCodeString", ""),
            pix_qrcode_imagem=pagamento.get("QrCodeBase64Image", ""),
            boleto_url=pagamento.get("Url", "") if pagamento.get("BarCodeNumber") else "",
            boleto_linha_digitavel=pagamento.get("DigitableLine", ""),
            bruto=corpo if isinstance(corpo, dict) else {"erros": corpo},
            http_status=http_status,
            endpoint=url,
            duracao_ms=ms,
        )

    def _cliente(self, pagamento) -> dict:
        """Dados do comprador, no formato que a Cielo espera."""
        pedido = pagamento.pedido
        usuario = getattr(pedido, "cliente", None)
        nome = (getattr(usuario, "get_full_name", lambda: "")() or "").strip()
        dados = {"Name": nome or "Cliente AgroCampo"}
        if getattr(usuario, "email", ""):
            dados["Email"] = usuario.email
        documento = (getattr(usuario, "cpf", "") or "").replace(".", "").replace("-", "")
        if documento:
            dados["Identity"] = documento
            dados["IdentityType"] = "CPF"
        return dados

    # ------------------------------------------------------------ cartão
    def autorizar_cartao(self, pagamento, cartao: DadosCartao, parcelas: int = 1):
        payload = {
            "MerchantOrderId": pagamento.pedido.numero,
            "Customer": self._cliente(pagamento),
            "Payment": {
                "Type": "CreditCard",
                "Amount": self.em_centavos(pagamento.valor),
                "Currency": "BRL",
                "Country": "BRA",
                "Installments": max(1, int(parcelas)),
                # captura automática é escolha do lojista no painel: com ela
                # desligada a venda fica autorizada esperando a separação
                "Capture": bool(self.provedor.captura_automatica),
                "SoftDescriptor": (self.provedor.soft_descriptor or "")[:13],
                "CreditCard": {
                    "CardNumber": cartao.numero.replace(" ", ""),
                    "Holder": cartao.nome,
                    "ExpirationDate": f"{cartao.validade_mes:02d}/{cartao.validade_ano}",
                    "SecurityCode": cartao.cvv,
                    "Brand": cartao.bandeira,
                    # guarda o cartão na Cielo e devolve um token: é ele que
                    # permite a cobrança automática da assinatura
                    "SaveCard": True,
                },
            },
        }
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["vendas"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        resultado.bandeira = resultado.bandeira or cartao.bandeira
        resultado.ultimos_digitos = resultado.ultimos_digitos or cartao.ultimos_digitos
        self._registrar(pagamento, "autorizacao", resultado, payload)
        return resultado

    def cobrar_com_token(self, pagamento, token: str):
        """Cobrança da assinatura com o cartão já salvo na Cielo."""
        payload = {
            "MerchantOrderId": pagamento.pedido.numero,
            "Customer": self._cliente(pagamento),
            "Payment": {
                "Type": "CreditCard",
                "Amount": self.em_centavos(pagamento.valor),
                "Currency": "BRL",
                "Country": "BRA",
                "Installments": 1,
                "Capture": True,
                "SoftDescriptor": (self.provedor.soft_descriptor or "")[:13],
                "CreditCard": {"CardToken": token},
            },
        }
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["vendas"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        self._registrar(pagamento, "cobranca_recorrente", resultado, payload)
        return resultado

    def tokenizar_cartao(self, usuario, cartao: DadosCartao):
        """Salva o cartão na Cielo e devolve o token em `referencia_externa`."""
        payload = {
            "CustomerName": cartao.nome,
            "CardNumber": cartao.numero.replace(" ", ""),
            "Holder": cartao.nome,
            "ExpirationDate": f"{cartao.validade_mes:02d}/{cartao.validade_ano}",
            "Brand": cartao.bandeira,
        }
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["cartao_salvo"], payload)
        token = (corpo or {}).get("CardToken", "") if isinstance(corpo, dict) else ""
        return ResultadoPagamento(
            sucesso=http < 400 and bool(token),
            status="autorizado" if token else "recusado",
            referencia_externa=token,
            mensagem=self._erros(corpo),
            bandeira=cartao.bandeira,
            ultimos_digitos=cartao.ultimos_digitos,
            bruto=corpo if isinstance(corpo, dict) else {"erros": corpo},
            http_status=http,
            endpoint=url,
            duracao_ms=ms,
        )

    # --------------------------------------------------------------- pix
    def criar_pix(self, pagamento):
        payload = {
            "MerchantOrderId": pagamento.pedido.numero,
            "Customer": self._cliente(pagamento),
            "Payment": {
                "Type": "Pix",
                "Amount": self.em_centavos(pagamento.valor),
            },
        }
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["vendas"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        self._registrar(pagamento, "pix", resultado, payload)
        return resultado

    # ------------------------------------------------------------ boleto
    def criar_boleto(self, pagamento):
        payload = {
            "MerchantOrderId": pagamento.pedido.numero,
            "Customer": self._cliente(pagamento),
            "Payment": {
                "Type": "Boleto",
                "Amount": self.em_centavos(pagamento.valor),
                "Provider": "bradesco2",
            },
        }
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["vendas"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        self._registrar(pagamento, "boleto", resultado, payload)
        return resultado

    # ------------------------------------------------- ciclo da transação
    def capturar(self, pagamento):
        caminho = ENDPOINTS["capturar"].format(id=pagamento.referencia_externa)
        http, corpo, ms, url = self._chamar("PUT", caminho)
        # a captura responde no nível raiz, não dentro de "Payment"
        corpo_normalizado = {"Payment": corpo} if isinstance(corpo, dict) else corpo
        resultado = self._resultado(http, corpo_normalizado, ms, url)
        resultado.referencia_externa = pagamento.referencia_externa
        self._registrar(pagamento, "captura", resultado)
        return resultado

    def consultar(self, pagamento):
        caminho = ENDPOINTS["venda"].format(id=pagamento.referencia_externa)
        http, corpo, ms, url = self._chamar("GET", caminho, consulta=True)
        resultado = self._resultado(http, corpo, ms, url)
        resultado.referencia_externa = pagamento.referencia_externa
        return resultado

    def estornar(self, pagamento, valor: Decimal = None):
        caminho = ENDPOINTS["cancelar"].format(id=pagamento.referencia_externa)
        if valor:
            caminho += f"?amount={self.em_centavos(valor)}"
        http, corpo, ms, url = self._chamar("PUT", caminho)
        corpo_normalizado = {"Payment": corpo} if isinstance(corpo, dict) else corpo
        resultado = self._resultado(http, corpo_normalizado, ms, url)
        resultado.referencia_externa = pagamento.referencia_externa
        self._registrar(pagamento, "estorno", resultado)
        return resultado

    # ----------------------------------------------------------- webhook
    def validar_webhook(self, corpo: bytes, assinatura: str) -> bool:
        """A notificação da Cielo não vem assinada.

        Ela avisa só o id e o tipo da mudança; o valor e o status vêm da
        consulta que a loja faz em seguida, com as próprias credenciais. É
        por isso que não há HMAC para conferir aqui — confiar no aviso sem
        consultar é que seria inseguro.
        """
        return True

    def interpretar_webhook(self, payload: dict) -> dict:
        """Normaliza o aviso da Cielo e busca o estado real na API.

        O corpo traz `PaymentId` e `ChangeType`. O status verdadeiro vem da
        consulta — o aviso diz que algo mudou, não o que ficou.
        """
        referencia = str(payload.get("PaymentId", ""))
        tipo = str(payload.get("ChangeType", ""))

        status = ""
        valor = None
        if referencia:
            caminho = ENDPOINTS["venda"].format(id=referencia)
            try:
                http, corpo, _, _ = self._chamar("GET", caminho, consulta=True)
                if http < 400 and isinstance(corpo, dict):
                    pagamento = corpo.get("Payment", {})
                    status = MAPA_STATUS.get(pagamento.get("Status"), "")
                    if pagamento.get("Amount"):
                        valor = Decimal(pagamento["Amount"]) / 100
            except ErroGateway:
                # Cielo fora do ar não pode derrubar o webhook: o evento fica
                # gravado e o painel reprocessa depois
                status = ""

        return {
            "referencia_externa": referencia,
            "status": status,
            "tipo": f"cielo.{tipo}" if tipo else "cielo",
            "valor": valor,
        }
