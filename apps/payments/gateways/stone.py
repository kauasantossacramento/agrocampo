"""Driver da Stone.

As credenciais vêm do `ProvedorPagamento` (banco de dados), nunca de
constantes no código. Os caminhos de endpoint estão centralizados em
`ENDPOINTS` para que uma mudança de contrato da Stone se resolva em um
único lugar.

Enquanto as credenciais não estiverem cadastradas, `apps.payments.gateways
.get_gateway()` devolve o driver simulado — o fluxo da loja funciona ponta
a ponta sem a Stone estar plugada.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

import requests
from django.utils import timezone

from .base import DadosCartao, ErroGateway, GatewayBase, ResultadoPagamento

# Caminhos da API. Ajuste aqui se o contrato da Stone mudar.
ENDPOINTS = {
    "token": "/auth/realms/stone_bank/protocol/openid-connect/token",
    "charges": "/v1/charges",
    "charge": "/v1/charges/{id}",
    "capture": "/v1/charges/{id}/capture",
    "cancel": "/v1/charges/{id}/cancel",
    "refunds": "/v1/charges/{id}/refunds",
    "pix": "/v1/pix/charges",
    "cards": "/v1/cards",
}

# status da Stone -> status do model Pagamento
MAPA_STATUS = {
    "pending": "pendente",
    "processing": "processando",
    "authorized": "autorizado",
    "paid": "pago",
    "succeeded": "pago",
    "captured": "pago",
    "failed": "recusado",
    "declined": "recusado",
    "refused": "recusado",
    "canceled": "cancelado",
    "cancelled": "cancelado",
    "refunded": "estornado",
    "partially_refunded": "estorno_parcial",
    "expired": "cancelado",
}


class StoneGateway(GatewayBase):
    codigo = "stone"

    # ------------------------------------------------------------- infra
    @property
    def base_url(self):
        return self.provedor.base_url.rstrip("/")

    def _headers(self, idempotency_key: str = "") -> dict:
        cabecalhos = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token()}",
            "User-Agent": "AgroCampo/1.0",
        }
        if self.provedor.stone_merchant_id:
            cabecalhos["X-Stone-Merchant-Id"] = self.provedor.stone_merchant_id
        if self.provedor.stone_affiliation_code:
            cabecalhos["X-Stone-Affiliation-Code"] = self.provedor.stone_affiliation_code
        if idempotency_key:
            cabecalhos["X-Idempotency-Key"] = idempotency_key
        return cabecalhos

    def _token(self) -> str:
        """Devolve o access token, renovando via OAuth quando necessário."""
        provedor = self.provedor
        if provedor.token_valido:
            return provedor.access_token

        if not (provedor.stone_client_id and provedor.stone_client_secret):
            # Integração por API Key pura, sem OAuth.
            return provedor.stone_api_key

        resposta = requests.post(
            f"{self.base_url}{ENDPOINTS['token']}",
            data={
                "grant_type": "client_credentials",
                "client_id": provedor.stone_client_id,
                "client_secret": provedor.stone_client_secret,
            },
            timeout=provedor.timeout_segundos,
        )
        if resposta.status_code >= 400:
            raise ErroGateway(
                "Falha ao autenticar na Stone.",
                resposta=self._json(resposta),
                http_status=resposta.status_code,
            )
        dados = self._json(resposta)
        provedor.access_token = dados.get("access_token", "")
        provedor.access_token_expira_em = timezone.now() + timedelta(
            seconds=int(dados.get("expires_in", 300)) - 30
        )
        provedor.save(update_fields=["access_token", "access_token_expira_em"])
        return provedor.access_token

    @staticmethod
    def _json(resposta):
        try:
            return resposta.json()
        except ValueError:
            return {"raw": resposta.text[:2000]}

    def _chamar(self, metodo, caminho, payload=None, idempotency_key=""):
        url = f"{self.base_url}{caminho}"
        with self._Cronometro() as crono:
            try:
                resposta = requests.request(
                    metodo,
                    url,
                    headers=self._headers(idempotency_key),
                    data=json.dumps(payload) if payload is not None else None,
                    timeout=self.provedor.timeout_segundos,
                )
            except requests.RequestException as exc:
                raise ErroGateway(f"Falha de comunicação com a Stone: {exc}") from exc
        corpo = self._json(resposta)
        return resposta.status_code, corpo, crono.ms, url

    # --------------------------------------------------------- traducoes
    def _resultado(self, http_status, corpo, ms, url) -> ResultadoPagamento:
        status_stone = str(corpo.get("status", "")).lower()
        status = MAPA_STATUS.get(status_stone, "processando")
        sucesso = http_status < 400 and status not in {"recusado", "cancelado"}
        cartao = corpo.get("card") or corpo.get("payment_method", {}).get("card") or {}
        return ResultadoPagamento(
            sucesso=sucesso,
            status=status,
            referencia_externa=str(corpo.get("id") or corpo.get("charge_id") or ""),
            mensagem=corpo.get("message") or corpo.get("error_description") or "",
            codigo_retorno=str(corpo.get("code") or corpo.get("acquirer_return_code") or ""),
            codigo_autorizacao=str(corpo.get("authorization_code") or ""),
            nsu=str(corpo.get("nsu") or corpo.get("acquirer_nsu") or ""),
            tid=str(corpo.get("tid") or corpo.get("acquirer_tid") or ""),
            bandeira=cartao.get("brand", ""),
            ultimos_digitos=cartao.get("last_four_digits", "") or cartao.get("last4", ""),
            bruto=corpo,
            http_status=http_status,
            endpoint=url,
            duracao_ms=ms,
        )

    def _cliente_payload(self, pedido):
        usuario = pedido.usuario
        endereco = pedido.endereco_entrega
        dados = {
            "name": pedido.nome_cliente,
            "email": pedido.email_cliente,
            "document": (usuario.cpf if usuario else "").replace(".", "").replace("-", ""),
            "phone": pedido.telefone_cliente,
        }
        if endereco:
            dados["address"] = {
                "street": endereco.logradouro,
                "number": endereco.numero,
                "complement": endereco.complemento,
                "neighborhood": endereco.bairro,
                "city": endereco.cidade,
                "state": endereco.uf,
                "zip_code": endereco.cep.replace("-", ""),
                "country": "BR",
            }
        return dados

    # --------------------------------------------------------- operacoes
    def autorizar_cartao(self, pagamento, cartao: DadosCartao, parcelas=1):
        payload = {
            "amount": self.em_centavos(pagamento.valor),
            "currency": "BRL",
            "capture": self.provedor.captura_automatica,
            "installments": parcelas,
            "soft_descriptor": self.provedor.soft_descriptor[:22],
            "reference_id": pagamento.pedido.numero,
            "payment_method": {
                "type": "credit_card",
                "card": {
                    "number": cartao.numero.replace(" ", ""),
                    "holder_name": cartao.nome,
                    "exp_month": cartao.validade_mes,
                    "exp_year": cartao.validade_ano,
                    "cvv": cartao.cvv,
                },
            },
            "customer": self._cliente_payload(pagamento.pedido),
        }
        chave = pagamento.idempotency_key or self.nova_idempotency_key()
        try:
            http_status, corpo, ms, url = self._chamar(
                "POST", ENDPOINTS["charges"], payload, chave
            )
        except ErroGateway as exc:
            self._registrar(pagamento, "autorizacao", None, payload, erro=str(exc))
            raise
        resultado = self._resultado(http_status, corpo, ms, url)
        resultado.bandeira = resultado.bandeira or cartao.bandeira
        resultado.ultimos_digitos = resultado.ultimos_digitos or cartao.ultimos_digitos
        self._registrar(pagamento, "autorizacao", resultado, payload)
        return resultado

    def cobrar_com_token(self, pagamento, token: str):
        payload = {
            "amount": self.em_centavos(pagamento.valor),
            "currency": "BRL",
            "capture": True,
            "installments": 1,
            "reference_id": pagamento.pedido.numero,
            "soft_descriptor": self.provedor.soft_descriptor[:22],
            "payment_method": {"type": "credit_card", "card_id": token},
            "recurrence": {"type": "subscription"},
            "customer": self._cliente_payload(pagamento.pedido),
        }
        http_status, corpo, ms, url = self._chamar(
            "POST", ENDPOINTS["charges"], payload, self.nova_idempotency_key()
        )
        resultado = self._resultado(http_status, corpo, ms, url)
        self._registrar(pagamento, "recorrencia", resultado, payload)
        return resultado

    def tokenizar_cartao(self, usuario, cartao: DadosCartao):
        payload = {
            "number": cartao.numero.replace(" ", ""),
            "holder_name": cartao.nome,
            "exp_month": cartao.validade_mes,
            "exp_year": cartao.validade_ano,
            "cvv": cartao.cvv,
            "holder_document": cartao.cpf_titular,
        }
        http_status, corpo, ms, url = self._chamar("POST", ENDPOINTS["cards"], payload)
        resultado = self._resultado(http_status, corpo, ms, url)
        resultado.bandeira = resultado.bandeira or cartao.bandeira
        resultado.ultimos_digitos = resultado.ultimos_digitos or cartao.ultimos_digitos
        resultado.sucesso = http_status < 400
        return resultado

    def criar_pix(self, pagamento):
        expira = self.provedor.pix_expira_em_minutos * 60
        payload = {
            "amount": self.em_centavos(pagamento.valor),
            "currency": "BRL",
            "reference_id": pagamento.pedido.numero,
            "expires_in": expira,
            "payment_method": {"type": "pix", "pix_key": self.provedor.stone_pix_chave},
            "customer": self._cliente_payload(pagamento.pedido),
        }
        chave = pagamento.idempotency_key or self.nova_idempotency_key()
        http_status, corpo, ms, url = self._chamar("POST", ENDPOINTS["pix"], payload, chave)
        resultado = self._resultado(http_status, corpo, ms, url)
        pix = corpo.get("pix") or corpo.get("qr_code") or {}
        resultado.pix_qrcode = pix.get("payload") or pix.get("emv") or corpo.get("qr_code_text", "")
        resultado.pix_qrcode_imagem = pix.get("image_url") or corpo.get("qr_code_url", "")
        resultado.pix_expira_em = timezone.now() + timedelta(seconds=expira)
        self._registrar(pagamento, "autorizacao", resultado, payload)
        return resultado

    def criar_boleto(self, pagamento):
        payload = {
            "amount": self.em_centavos(pagamento.valor),
            "currency": "BRL",
            "reference_id": pagamento.pedido.numero,
            "payment_method": {"type": "boleto"},
            "customer": self._cliente_payload(pagamento.pedido),
        }
        http_status, corpo, ms, url = self._chamar("POST", ENDPOINTS["charges"], payload)
        resultado = self._resultado(http_status, corpo, ms, url)
        boleto = corpo.get("boleto", {})
        resultado.boleto_url = boleto.get("url", "")
        resultado.boleto_linha_digitavel = boleto.get("line", "")
        self._registrar(pagamento, "autorizacao", resultado, payload)
        return resultado

    def capturar(self, pagamento):
        caminho = ENDPOINTS["capture"].format(id=pagamento.referencia_externa)
        payload = {"amount": self.em_centavos(pagamento.valor)}
        http_status, corpo, ms, url = self._chamar("POST", caminho, payload)
        resultado = self._resultado(http_status, corpo, ms, url)
        self._registrar(pagamento, "captura", resultado, payload)
        return resultado

    def consultar(self, pagamento):
        caminho = ENDPOINTS["charge"].format(id=pagamento.referencia_externa)
        http_status, corpo, ms, url = self._chamar("GET", caminho)
        resultado = self._resultado(http_status, corpo, ms, url)
        self._registrar(pagamento, "consulta", resultado)
        return resultado

    def estornar(self, pagamento, valor: Decimal):
        caminho = ENDPOINTS["refunds"].format(id=pagamento.referencia_externa)
        payload = {"amount": self.em_centavos(valor)}
        http_status, corpo, ms, url = self._chamar(
            "POST", caminho, payload, self.nova_idempotency_key()
        )
        resultado = self._resultado(http_status, corpo, ms, url)
        resultado.sucesso = http_status < 400
        self._registrar(pagamento, "estorno", resultado, payload)
        return resultado

    # ---------------------------------------------------------- webhooks
    def validar_webhook(self, corpo: bytes, assinatura: str) -> bool:
        segredo = self.provedor.stone_webhook_secret
        if not segredo:
            return False
        esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        recebido = (assinatura or "").split("=")[-1].strip()
        return hmac.compare_digest(esperado, recebido)

    def interpretar_webhook(self, payload: dict) -> dict:
        dados = payload.get("data") or payload.get("object") or payload
        status_stone = str(dados.get("status", "")).lower()
        valor = dados.get("amount")
        return {
            "tipo": payload.get("type") or payload.get("event") or "",
            "referencia_externa": str(dados.get("id") or dados.get("charge_id") or ""),
            "status": MAPA_STATUS.get(status_stone, ""),
            "valor": Decimal(valor) / 100 if valor else None,
            "e2e_id": dados.get("end_to_end_id", ""),
        }
