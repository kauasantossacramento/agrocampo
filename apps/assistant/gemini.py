"""Cliente mínimo da API do Gemini (Google AI Studio), sem SDK.

Uma chamada HTTP só: `generateContent`. Não vale puxar o SDK do Google
para isso — o `requests` já está no projeto e a resposta é um JSON simples.
"""
import logging

import requests

log = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 25


class GeminiErro(Exception):
    pass


def gerar_resposta(*, chave: str, modelo: str, instrucoes: str, historico: list[dict]) -> str:
    """Envia o histórico e devolve o texto da resposta.

    `historico` é uma lista de {"papel": "usuario"|"assistente", "texto": "..."}
    — a última entrada é a pergunta atual.
    """
    if not chave:
        raise GeminiErro("Chave do Gemini não cadastrada.")

    contents = [
        {
            "role": "user" if m["papel"] == "usuario" else "model",
            "parts": [{"text": m["texto"]}],
        }
        for m in historico
        if m.get("texto")
    ]
    corpo = {
        "system_instruction": {"parts": [{"text": instrucoes}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 600,
        },
        # a loja vende ração e remédio de animal; os filtros padrão às vezes
        # travam em "vermífugo" ou "carrapaticida" — afrouxa só o necessário
        "safetySettings": [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ],
    }

    try:
        resposta = requests.post(
            f"{BASE}/{modelo}:generateContent",
            params={"key": chave},
            json=corpo,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GeminiErro(f"Sem resposta do Gemini: {exc}") from exc

    if resposta.status_code != 200:
        try:
            detalhe = resposta.json().get("error", {}).get("message", "")
        except ValueError:
            detalhe = resposta.text[:200]
        log.warning("Gemini %s: %s", resposta.status_code, detalhe)
        raise GeminiErro(f"Gemini respondeu {resposta.status_code}: {detalhe}")

    dados = resposta.json()
    try:
        candidato = dados["candidates"][0]
        partes = candidato["content"]["parts"]
        texto = "".join(p.get("text", "") for p in partes).strip()
    except (KeyError, IndexError, TypeError):
        motivo = (dados.get("promptFeedback") or {}).get("blockReason", "")
        raise GeminiErro(f"Resposta vazia do Gemini{f' ({motivo})' if motivo else ''}.")

    if not texto:
        raise GeminiErro("Resposta vazia do Gemini.")
    return texto
