# Serviço de WhatsApp Web

Mantém uma sessão do WhatsApp Web no servidor e envia os avisos de pedido
(confirmado, item em falta, saiu para entrega) para o cliente.

> **Risco, dito sem rodeios:** isto não é a API oficial da Meta. Controlar
> o WhatsApp Web por robô viola os Termos de Serviço e o número da loja pode
> ser banido — inclusive o número que os clientes já conhecem. O lojista
> optou por este caminho ciente disso. O interruptor fica em
> **Painel › Configurações › WhatsApp**; desligado, os avisos param e o
> link `wa.me` (manual) continua funcionando.

## Como funciona

```
Django (web)  --POST /enviar-->  whatsapp (Node + Chromium)  -->  WhatsApp Web
              <--GET /status--   (QR Code para parear, estado da sessão)
```

- Sessão persistida no volume `whatsapp_sessao`; sobrevive a restart.
- Só responde na rede interna do compose; o token (`WHATSAPP_WEB_TOKEN`) é a
  única barreira, por isso o serviço se recusa a subir sem ele.
- O Django espera no máximo 8 s; se o serviço estiver fora, o pedido segue
  normalmente e a mensagem fica registrada como *falhou* no painel.

## Parear

1. Suba o stack (`docker compose up -d whatsapp`).
2. Painel › Configurações › aba **WhatsApp** — aparece o QR Code.
3. No celular da loja: WhatsApp › Aparelhos conectados › Conectar aparelho.
4. Quando o painel mostrar *conectado*, ligue o interruptor e salve.

Recomendação: use um chip **dedicado** à loja, não o pessoal de alguém.
Se esse número cair, o principal continua intacto.

## Variáveis

| Variável | Onde | Para quê |
|---|---|---|
| `WHATSAPP_WEB_TOKEN` | `.env` (web e whatsapp) | segredo compartilhado; gere com `openssl rand -hex 32` |
| `WHATSAPP_WEB_URL` | web | `http://whatsapp:3000` no compose |
| `SITE_URL` | web | prefixo dos links enviados (`https://agrocampo.online`) |

## Se o WhatsApp mudar o protocolo

`whatsapp-web.js` quebra de tempos em tempos quando o WhatsApp Web muda.
Sintoma: estado `erro` ou `aguardando_qr` que nunca conecta. Solução:
atualizar a dependência (`npm update whatsapp-web.js`) e rebuildar
(`docker compose build whatsapp && docker compose up -d --no-deps whatsapp`).
