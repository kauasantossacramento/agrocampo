"""Driver da Pagar.me — API v5.

A loja escolhe o adquirente em Configurações › Pagamentos. O resto do
sistema não sabe a diferença: fala com `GatewayBase` e recebe
`ResultadoPagamento`.

Quatro coisas separam a Pagar.me da Stone e da Cielo e explicam o formato
deste arquivo:

* **Autenticação Basic, sem OAuth e sem token a renovar.** A chave secreta
  vai como usuário e a senha fica vazia, em toda requisição.
* **Um endereço só.** `https://api.pagar.me/core/v5` atende transação e
  consulta. Não há host de sandbox: quem separa teste de produção é a
  *chave* — a de teste não gera recebível. Por isso o campo "ambiente" do
  provedor aqui significa "qual par de chaves usar", não outra URL.
* **Pedido e cobrança são coisas diferentes.** Cria-se um *pedido*
  (`/orders`) e ele nasce com uma ou mais *cobranças* (`charges`). Quem
  tem id, status, captura e estorno é a cobrança — é o `ch_...` que vai
  para `Pagamento.referencia_externa`.
* **Dois níveis de status.** A cobrança diz `paid`, `pending`, `canceled`;
  a transação dentro dela diz `authorized_pending_capture`, `refunded`,
  `partial_refunded`. O estado fino está na transação, então ele tem a
  palavra final quando os dois discordam.

Referência: https://docs.pagar.me/reference/criar-pedido-2
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from django.utils import timezone

from .base import DadosCartao, ErroGateway, GatewayBase, ResultadoPagamento

# Caminhos da API. Mudança de contrato se resolve aqui, num lugar só.
ENDPOINTS = {
    "pedidos": "/orders",
    "pedido": "/orders/{id}",
    "cobranca": "/charges/{id}",
    "capturar": "/charges/{id}/capture",
    "cancelar": "/charges/{id}",
    "clientes": "/customers",
    "cartoes": "/customers/{id}/cards",
}

# status da cobrança -> status do model Pagamento
MAPA_STATUS = {
    "pending": "pendente",
    "processing": "processando",
    "paid": "pago",
    "overpaid": "pago",
    "underpaid": "pendente",
    "canceled": "cancelado",
    "failed": "recusado",
    "not_paid": "recusado",
    "waiting_payment": "pendente",
    "chargedback": "estornado",
}

# status da transação -> status do model Pagamento. Mais fino que o da
# cobrança: só aqui aparece "autorizado sem captura" e o estorno parcial.
MAPA_TRANSACAO = {
    "authorized_pending_capture": "autorizado",
    "waiting_capture": "autorizado",
    "captured": "pago",
    "partial_capture": "pago",
    "paid": "pago",
    "waiting_payment": "pendente",
    "generated": "pendente",
    "not_authorized": "recusado",
    "with_error": "recusado",
    "failed": "recusado",
    "refunded": "estornado",
    "partial_refunded": "estorno_parcial",
    "voided": "cancelado",
    "partial_void": "estorno_parcial",
    "chargedback": "estornado",
    # estados de "ainda mexendo": não viram nada definitivo na loja
    "waiting_cancellation": "processando",
    "error_on_voiding": "processando",
    "error_on_refunding": "processando",
}

# prazo e instrução do boleto. Não são cadastráveis porque o lojista não
# emite boleto hoje (`aceita_boleto` nasce desligado); vira campo no dia em
# que ele ligar e pedir outro prazo.
BOLETO_DIAS = 3
BOLETO_INSTRUCOES = "Não receber após o vencimento."

# eventos de webhook que interessam ao pedido
EVENTOS_CONHECIDOS = {
    "charge.paid", "charge.payment_failed", "charge.pending",
    "charge.refunded", "charge.created", "charge.updated",
    "order.paid", "order.payment_failed", "order.canceled", "order.created",
}


class PagarmeGateway(GatewayBase):
    codigo = "pagarme"

    # ------------------------------------------------------------- infra
    @property
    def base_url(self):
        return (self.provedor.pagarme_base_url or "").rstrip("/")

    def _auth(self):
        """Basic com a chave secreta no usuário e senha vazia."""
        return (self.provedor.pagarme_secret_key, "")

    def _chamar(self, metodo, caminho, payload=None, auth=None, params=None):
        """Uma chamada à Pagar.me, com o tempo medido."""
        url = f"{self.base_url}{caminho}"
        with self._Cronometro() as crono:
            try:
                resposta = requests.request(
                    metodo,
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "AgroCampo/1.0",
                    },
                    auth=self._auth() if auth is None else auth,
                    params=params,
                    data=json.dumps(payload) if payload is not None else None,
                    timeout=self.provedor.timeout_segundos,
                )
            except requests.RequestException as exc:
                raise ErroGateway(f"Falha de comunicação com a Pagar.me: {exc}") from exc

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
        """O erro vem em `message` e, quando é de validação, em `errors`.

        `errors` é um dicionário de campo -> lista de frases; jogar isso
        cru na tela do cliente não ajuda ninguém, então vira uma linha.
        """
        if not isinstance(corpo, dict):
            return ""
        partes = []
        if corpo.get("message"):
            partes.append(str(corpo["message"]))
        erros = corpo.get("errors")
        if isinstance(erros, dict):
            for campo, frases in erros.items():
                texto = frases if isinstance(frases, str) else " ".join(map(str, frases))
                partes.append(f"{campo}: {texto}")
        elif isinstance(erros, list):
            partes.extend(str(e) for e in erros)
        return " · ".join(partes)[:250]

    @staticmethod
    def _cobranca(corpo):
        """Acha a cobrança, venha ela de /orders ou de /charges."""
        if not isinstance(corpo, dict):
            return {}
        cobrancas = corpo.get("charges")
        if isinstance(cobrancas, list) and cobrancas:
            return cobrancas[0] or {}
        # /charges/{id} e a captura devolvem a própria cobrança
        if corpo.get("id") or corpo.get("status"):
            return corpo
        return {}

    @staticmethod
    def _motivo(transacao) -> str:
        """O porquê da recusa, em uma linha, quando a API não mandou erro.

        Cartão recusado não é erro de requisição: volta 200 com a transação
        reprovada, e o motivo fica em `gateway_response.errors`.
        """
        resposta = transacao.get("gateway_response")
        if isinstance(resposta, dict):
            erros = resposta.get("errors")
            if isinstance(erros, list) and erros:
                frases = [
                    str(e.get("message", "")) if isinstance(e, dict) else str(e)
                    for e in erros
                ]
                return " · ".join(f for f in frases if f)[:250]
        return str(transacao.get("acquirer_message", ""))[:250]

    @staticmethod
    def _quando(texto):
        """Converte a data ISO da Pagar.me em datetime com fuso."""
        if not texto:
            return None
        try:
            momento = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
        except ValueError:
            return None
        if timezone.is_naive(momento):
            momento = timezone.make_aware(momento, timezone.utc)
        return momento

    def _resultado(self, http_status, corpo, ms, url) -> ResultadoPagamento:
        cobranca = self._cobranca(corpo)
        transacao = cobranca.get("last_transaction") or {}

        # o estado fino está na transação; a cobrança é o guarda-chuva
        status = MAPA_TRANSACAO.get(transacao.get("status") or "") or MAPA_STATUS.get(
            cobranca.get("status") or "", "processando"
        )

        erro = self._erros(corpo)
        sucesso = (
            http_status < 400
            and status not in {"recusado", "cancelado"}
            and transacao.get("success", True) is not False
        )

        cartao = transacao.get("card") or {}
        return ResultadoPagamento(
            sucesso=sucesso,
            status=status,
            referencia_externa=str(cobranca.get("id", "")),
            mensagem=erro or self._motivo(transacao),
            codigo_retorno=str(transacao.get("acquirer_return_code", "")),
            codigo_autorizacao=str(transacao.get("acquirer_auth_code", "")),
            nsu=str(transacao.get("acquirer_nsu", "")),
            tid=str(transacao.get("acquirer_tid", "")),
            bandeira=cartao.get("brand", ""),
            ultimos_digitos=cartao.get("last_four_digits", ""),
            pix_qrcode=transacao.get("qr_code", ""),
            pix_qrcode_imagem=transacao.get("qr_code_url", ""),
            pix_expira_em=self._quando(transacao.get("expires_at")),
            boleto_url=transacao.get("pdf") or transacao.get("url", ""),
            boleto_linha_digitavel=transacao.get("line", ""),
            bruto=corpo if isinstance(corpo, dict) else {"resposta": corpo},
            http_status=http_status,
            endpoint=url,
            duracao_ms=ms,
        )

    # ------------------------------------------------------ dados da loja
    def _cliente(self, pagamento) -> dict:
        """O comprador, com os dados congelados no pedido.

        São os do momento da compra — o cliente pode trocar o telefone no
        cadastro depois, e a cobrança tem que continuar contando a história
        de quando foi feita.
        """
        pedido = pagamento.pedido
        usuario = getattr(pedido, "usuario", None)

        dados = {
            "name": (pedido.nome_cliente or "").strip()[:64] or "Cliente AgroCampo",
            "type": "individual",
        }
        if pedido.email_cliente:
            dados["email"] = pedido.email_cliente

        documento = "".join(c for c in (getattr(usuario, "cpf", "") or "") if c.isdigit())
        if documento:
            dados["document"] = documento
            dados["document_type"] = "CNPJ" if len(documento) > 11 else "CPF"

        telefone = "".join(c for c in (pedido.telefone_cliente or "") if c.isdigit())
        if len(telefone) >= 10:
            dados["phones"] = {
                "mobile_phone": {
                    "country_code": "55",
                    "area_code": telefone[-11:-9] or telefone[:2],
                    "number": telefone[-9:],
                }
            }
        return dados

    def _itens(self, pagamento) -> list:
        """Uma linha só, com o total do pedido.

        A Pagar.me soma os itens para fechar o valor do pedido. Mandar o
        carrinho item a item faria a soma brigar com o total sempre que
        houvesse frete, desconto de Pix ou arredondamento de parcela — e
        quem manda no valor cobrado é o `Pagamento`.
        """
        return [
            {
                "code": pagamento.pedido.numero[:52],
                "description": f"Pedido {pagamento.pedido.numero}"[:255],
                "quantity": 1,
                "amount": self.em_centavos(pagamento.valor),
            }
        ]

    def _pedido(self, pagamento, pagamentos: list) -> dict:
        return {
            "code": pagamento.pedido.numero[:52],
            "closed": True,
            "customer": self._cliente(pagamento),
            "items": self._itens(pagamento),
            "payments": pagamentos,
        }

    # ------------------------------------------------------------ cartão
    def autorizar_cartao(self, pagamento, cartao: DadosCartao, parcelas: int = 1):
        documento = "".join(c for c in (cartao.cpf_titular or "") if c.isdigit())
        dados_cartao = {
            "number": cartao.numero.replace(" ", ""),
            "holder_name": cartao.nome,
            "exp_month": int(cartao.validade_mes),
            "exp_year": int(cartao.validade_ano),
            "cvv": cartao.cvv,
        }
        if documento:
            dados_cartao["holder_document"] = documento

        payload = self._pedido(
            pagamento,
            [
                {
                    "payment_method": "credit_card",
                    "amount": self.em_centavos(pagamento.valor),
                    "credit_card": {
                        # com a captura automática desligada a venda fica
                        # autorizada esperando a separação do pedido
                        "operation_type": (
                            "auth_and_capture"
                            if self.provedor.captura_automatica
                            else "auth_only"
                        ),
                        "installments": max(1, int(parcelas)),
                        "statement_descriptor": (self.provedor.soft_descriptor or "")[:13],
                        "card": dados_cartao,
                    },
                }
            ],
        )
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["pedidos"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        resultado.bandeira = resultado.bandeira or cartao.bandeira
        resultado.ultimos_digitos = resultado.ultimos_digitos or cartao.ultimos_digitos
        self._registrar(pagamento, "autorizacao", resultado, payload)
        return resultado

    def cobrar_com_token(self, pagamento, token: str):
        """Cobrança da assinatura com o cartão já salvo na Pagar.me.

        O token guardado é `cus_...|card_...`: a Pagar.me amarra o cartão
        ao cliente, e cobrar exige os dois. Veja `tokenizar_cartao`.
        """
        cliente_id, _, cartao_id = (token or "").partition("|")
        if not cartao_id:
            # token antigo, gravado antes de a amarração existir
            cartao_id, cliente_id = cliente_id, ""

        payload = {
            "code": pagamento.pedido.numero[:52],
            "closed": True,
            "items": self._itens(pagamento),
            "payments": [
                {
                    "payment_method": "credit_card",
                    "amount": self.em_centavos(pagamento.valor),
                    "credit_card": {
                        "operation_type": "auth_and_capture",
                        "installments": 1,
                        "statement_descriptor": (self.provedor.soft_descriptor or "")[:13],
                        "card_id": cartao_id,
                        # cobrança recorrente: sem CVV, e avisando que não é
                        # o cliente quem está na tela
                        "recurrence_cycle": "subsequent",
                    },
                }
            ],
        }
        if cliente_id:
            payload["customer_id"] = cliente_id
        else:
            payload["customer"] = self._cliente(pagamento)

        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["pedidos"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        self._registrar(pagamento, "cobranca_recorrente", resultado, payload)
        return resultado

    def tokenizar_cartao(self, usuario, cartao: DadosCartao):
        """Salva o cartão e devolve `cus_...|card_...` em `referencia_externa`.

        São duas chamadas porque a Pagar.me não guarda cartão solto: ele
        pertence a um cliente. O par volta junto porque a cobrança depois
        precisa dos dois, e o cadastro da loja só tem um campo de token.
        """
        nome = (usuario.get_full_name() or usuario.email or "Cliente").strip()
        documento = "".join(c for c in (getattr(usuario, "cpf", "") or "") if c.isdigit())

        corpo_cliente = {"name": nome[:64], "type": "individual"}
        if usuario.email:
            corpo_cliente["email"] = usuario.email
        if documento:
            corpo_cliente["document"] = documento
            corpo_cliente["document_type"] = "CNPJ" if len(documento) > 11 else "CPF"

        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["clientes"], corpo_cliente)
        cliente_id = str((corpo or {}).get("id", "")) if isinstance(corpo, dict) else ""
        if http >= 400 or not cliente_id:
            return ResultadoPagamento(
                sucesso=False,
                status="recusado",
                mensagem=self._erros(corpo) or "Não foi possível salvar o cliente.",
                bruto=corpo if isinstance(corpo, dict) else {},
                http_status=http,
                endpoint=url,
                duracao_ms=ms,
            )

        corpo_cartao = {
            "number": cartao.numero.replace(" ", ""),
            "holder_name": cartao.nome,
            "exp_month": int(cartao.validade_mes),
            "exp_year": int(cartao.validade_ano),
            "cvv": cartao.cvv,
        }
        if documento:
            corpo_cartao["holder_document"] = documento

        caminho = ENDPOINTS["cartoes"].format(id=cliente_id)
        http, corpo, ms, url = self._chamar("POST", caminho, corpo_cartao)
        cartao_id = str((corpo or {}).get("id", "")) if isinstance(corpo, dict) else ""

        return ResultadoPagamento(
            sucesso=http < 400 and bool(cartao_id),
            status="autorizado" if cartao_id else "recusado",
            referencia_externa=f"{cliente_id}|{cartao_id}" if cartao_id else "",
            mensagem=self._erros(corpo),
            bandeira=(corpo or {}).get("brand", "") if isinstance(corpo, dict) else "",
            ultimos_digitos=(corpo or {}).get("last_four_digits", "")
            if isinstance(corpo, dict)
            else "",
            bruto=corpo if isinstance(corpo, dict) else {},
            http_status=http,
            endpoint=url,
            duracao_ms=ms,
        )

    # --------------------------------------------------------------- pix
    def criar_pix(self, pagamento):
        payload = self._pedido(
            pagamento,
            [
                {
                    "payment_method": "pix",
                    "amount": self.em_centavos(pagamento.valor),
                    "pix": {
                        "expires_in": int(self.provedor.pix_expira_em_minutos) * 60,
                    },
                }
            ],
        )
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["pedidos"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        if not resultado.pix_expira_em:
            resultado.pix_expira_em = timezone.now() + timedelta(
                minutes=self.provedor.pix_expira_em_minutos
            )
        self._registrar(pagamento, "pix", resultado, payload)
        return resultado

    # ------------------------------------------------------------ boleto
    def criar_boleto(self, pagamento):
        vencimento = timezone.now() + timedelta(days=BOLETO_DIAS)
        payload = self._pedido(
            pagamento,
            [
                {
                    "payment_method": "boleto",
                    "amount": self.em_centavos(pagamento.valor),
                    "boleto": {
                        "instructions": BOLETO_INSTRUCOES,
                        "due_at": vencimento.date().isoformat(),
                    },
                }
            ],
        )
        http, corpo, ms, url = self._chamar("POST", ENDPOINTS["pedidos"], payload)
        resultado = self._resultado(http, corpo, ms, url)
        self._registrar(pagamento, "boleto", resultado, payload)
        return resultado

    # ------------------------------------------------- ciclo da transação
    def capturar(self, pagamento):
        caminho = ENDPOINTS["capturar"].format(id=pagamento.referencia_externa)
        payload = {"amount": self.em_centavos(pagamento.valor)}
        http, corpo, ms, url = self._chamar("POST", caminho, payload)
        resultado = self._resultado(http, corpo, ms, url)
        resultado.referencia_externa = pagamento.referencia_externa
        self._registrar(pagamento, "captura", resultado, payload)
        return resultado

    def consultar(self, pagamento):
        caminho = ENDPOINTS["cobranca"].format(id=pagamento.referencia_externa)
        http, corpo, ms, url = self._chamar("GET", caminho)
        resultado = self._resultado(http, corpo, ms, url)
        resultado.referencia_externa = pagamento.referencia_externa
        return resultado

    def estornar(self, pagamento, valor: Decimal = None):
        """Cancelamento e estorno são a mesma porta na Pagar.me.

        Antes da captura o DELETE cancela; depois, estorna. Sem `amount` o
        valor é o total da cobrança; com ele, é estorno parcial.
        """
        caminho = ENDPOINTS["cancelar"].format(id=pagamento.referencia_externa)
        payload = {"amount": self.em_centavos(valor)} if valor else None
        http, corpo, ms, url = self._chamar("DELETE", caminho, payload)
        resultado = self._resultado(http, corpo, ms, url)
        resultado.referencia_externa = pagamento.referencia_externa
        self._registrar(pagamento, "estorno", resultado, payload or {})
        return resultado

    # ----------------------------------------------------------- webhook
    def validar_webhook(self, corpo: bytes, assinatura: str) -> bool:
        """A Pagar.me não assina a notificação.

        A proteção que ela oferece é um usuário e senha Basic no endereço
        cadastrado no painel — isso é conferido na view, que tem o
        cabeçalho em mãos. Aqui o que garante a verdade é outra coisa: o
        status vale o que a consulta à API disser, não o que o aviso
        afirma. Veja `interpretar_webhook`.
        """
        return True

    def interpretar_webhook(self, payload: dict) -> dict:
        """Normaliza o aviso e confirma o estado real na API.

        O corpo traz `type` e `data` com o objeto já quase inteiro, mas
        aceitar valor e status de quem bate na porta é confiar no remetente
        errado — a palavra final vem de `GET /charges/{id}`, feito com a
        chave secreta da loja.
        """
        tipo = str(payload.get("type", "")) or "pagarme"
        dados = payload.get("data") or {}
        if not isinstance(dados, dict):
            dados = {}

        # evento de pedido traz as cobranças dentro; o de cobrança é a
        # própria cobrança
        cobranca = self._cobranca(dados) if dados.get("charges") else dados
        referencia = str(cobranca.get("id", ""))

        status = ""
        valor = None
        e2e = ""
        if referencia:
            caminho = ENDPOINTS["cobranca"].format(id=referencia)
            try:
                http, corpo, _, _ = self._chamar("GET", caminho)
                if http < 400 and isinstance(corpo, dict):
                    confirmada = self._cobranca(corpo)
                    transacao = confirmada.get("last_transaction") or {}
                    status = MAPA_TRANSACAO.get(
                        transacao.get("status") or ""
                    ) or MAPA_STATUS.get(confirmada.get("status") or "", "")
                    bruto = confirmada.get("paid_amount") or confirmada.get("amount")
                    if bruto:
                        valor = Decimal(bruto) / 100
                    e2e = transacao.get("end_to_end_id", "") or ""
            except ErroGateway:
                # Pagar.me fora do ar não pode derrubar o webhook: o evento
                # fica gravado e o painel reprocessa depois
                status = ""

        return {
            "referencia_externa": referencia,
            "status": status,
            "tipo": tipo if tipo in EVENTOS_CONHECIDOS else f"pagarme.{tipo}",
            "valor": valor,
            "e2e_id": e2e,
        }
