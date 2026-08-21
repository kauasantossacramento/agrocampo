# Veterinária AgroCampo — E-commerce

Loja completa para ração, saúde animal, aves e insumos rurais, com
**assinatura recorrente** e **gateway de pagamento próprio conectado à Stone**.

Backend em **Django 5 + DRF**. Storefront server-rendered com design system
próprio (tokens CSS, animações e interações consistentes). A camada DRF existe
em paralelo para alimentar o PWA/app mobile.

---

## Subir o projeto

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

cp .env.example .env              # ajuste o que precisar
python manage.py migrate
python manage.py seed             # catálogo, banners, blog e páginas
python manage.py criar_usuarios_demo
python manage.py criar_pedidos_demo   # opcional: popula o painel do lojista
python manage.py runserver
```

| Perfil | E-mail | Senha |
|---|---|---|
| Admin | `admin@agrocampo.com.br` | `agrocampo123` |
| Lojista | `lojista@agrocampo.com.br` | `agrocampo123` |
| Cliente | `cliente@agrocampo.com.br` | `agrocampo123` |

Rotas principais: `/` (loja) · `/painel/` (lojista) · `/admin/` (Django) ·
`/api/v1/` (API).

---

## Conectar a Stone

O adquirente é configurado **pelo banco de dados**, não por deploy.

1. Entre em **Painel › Configurações › Editar credenciais** (ou
   `/admin/payments/provedorpagamento/`).
2. Preencha os campos da seção *Credenciais Stone*:

| Campo | Para que serve |
|---|---|
| `stone_client_id` / `stone_client_secret` | OAuth `client_credentials` (opcional se usar só API Key) |
| `stone_api_key` | **Obrigatório** — header `Authorization` |
| `stone_merchant_id` | **Obrigatório** — identificador do estabelecimento |
| `stone_affiliation_code` | Stone Code / código de afiliação |
| `stone_webhook_secret` | Valida a assinatura HMAC-SHA256 das notificações |
| `stone_pix_chave` | Chave Pix do recebedor, usada no BR Code |
| `stone_base_url_sandbox` / `_producao` | URLs por ambiente |

3. Troque **Driver** para `Stone` e **Ambiente** para `sandbox` ou `producao`.
4. Cadastre a URL do webhook no painel da Stone:
   `https://SEU-DOMINIO/pagamentos/webhook/stone/`

**Fallback seguro:** se o driver for `Stone` mas faltar API Key ou Merchant ID,
`get_gateway()` cai automaticamente no driver **simulado** — o checkout não
quebra por configuração incompleta.

### Modo simulado

Permite rodar o fluxo inteiro sem a Stone plugada:

- cartão terminado em `0000` → recusado;
- terminado em `1111` → autorizado, sem captura;
- qualquer outro → aprovado;
- Pix → gera um BR Code válido em formato (CRC-16/CCITT do BACEN), confirmado
  pelo botão *Simular confirmação* na tela do QR Code.

### Arquitetura de pagamentos

```
views/services  →  gateways.get_gateway()  →  StoneGateway | SimuladoGateway
                                                     ↓
                        ProvedorPagamento (credenciais, no banco)
                        Pagamento          (ciclo de vida da loja)
                        TransacaoPagamento (trilha bruta de auditoria)
                        EventoWebhook      (evento cru, reprocessável)
                        Estorno / CartaoTokenizado
```

O resto do sistema nunca fala com a Stone diretamente — só com
`apps/payments/services.py`.

**Dados sensíveis:** PAN, CVV e segredos são mascarados antes de qualquer
persistência (`GatewayBase._mascarar`). A loja guarda apenas bandeira, 4
últimos dígitos e o token devolvido pela Stone.

---

## Fluxo do pedido

```
aguardando_pagamento → pago → aguardando_aprovação
                                    ├── aprovado → em_separação → enviado → entregue
                                    └── recusado → (sugestões de similares | estorno)
```

Transições inválidas levantam erro em `Pedido.mudar_status()`. Cada mudança
grava um `EventoPedido`, que alimenta a timeline do cliente e do lojista.

O estoque **só é baixado na aprovação do lojista** — nunca no pagamento. Isso
evita reservar estoque de um pedido que a loja pode não conseguir atender.

---

## Assinaturas

Itens marcados como recorrentes viram `Assinatura` quando o primeiro pedido é
aprovado. Cada entrega gera um `CicloAssinatura` que cobra o cartão tokenizado
e cria um pedido normal, que passa pelo mesmo fluxo de aprovação.

Agende diariamente:

```bash
python manage.py processar_assinaturas
python manage.py processar_assinaturas --dry-run   # só lista
```

Três falhas consecutivas cancelam a assinatura; antes disso, nova tentativa em
3 dias.

---

## Estrutura

```
config/           settings, urls, api_urls
apps/
  core/           SiteConfig, banners, diferenciais, páginas, newsletter
  accounts/       User (login por e-mail), Endereco
  catalog/        Categoria (hierárquica), Marca, Especie, Produto, estoque
  cart/           Carrinho de sessão + merge no login
  orders/         Pedido, máquina de estados, timeline, cupons
  payments/       ProvedorPagamento, Pagamento, gateways/, webhooks, estornos
  subscriptions/  Assinatura, CicloAssinatura
  notifications/  Notificação in-app + e-mail
  dashboard/      Painel do lojista
  blog/           Posts e categorias
static/css/       design-system.css · motion.css · layout.css
templates/        base + partials + uma pasta por app
```

---

## Design system

Tokens em `static/css/design-system.css`. Nada de cor ou espaço hard-coded nos
componentes.

| Token | Valor |
|---|---|
| `--red` / `--red-dark` | `#D62B20` / `#A81F17` |
| `--yellow` | `#FFC72C` |
| `--ink` | `#221812` |
| `--cream` / `--cream-warm` | `#FFF8F0` / `#FFF1E4` |
| `--green` | `#2F9E44` |

Tipografia: **Poppins** 600–800 (títulos), **Inter** 400–700 (texto).

`motion.css` concentra as animações: uma curva de entrada (`--ease-out`), uma
de micro-interação (`--ease-quick`), revelação ao rolar via
`IntersectionObserver` com cascata, e `prefers-reduced-motion` respeitado em
todo o arquivo.

### Responsivo

`responsive.css` é carregado por último e concentra **todas** as regras que
mudam por largura — não há media query espalhada pelos outros arquivos.

| Breakpoint | O que muda |
|---|---|
| ≤1180px | menu de categorias compacta o espaçamento |
| ≤980px | menu vira drawer, topbar reduz aos essenciais, painel empilha |
| ≤860px | filtros do catálogo viram acordeão fechado |
| ≤620px | grades caem para 2 colunas, tabelas rolam no container |
| ≤420px | vitrine mantém 2 colunas (padrão mobile), pares de conteúdo empilham |
| ≤340px | tudo em 1 coluna |

Auditado com emulação real de device via CDP: **19 páginas × 9 larguras
(320→1440), zero overflow horizontal**. O script fica em
`scratchpad/audit.py` do ambiente de desenvolvimento.

> Cuidado ao testar: `msedge --headless --window-size=390` **não** entrega um
> viewport de 390px — o Windows clampa a janela em ~500px e o resultado
> engana. Use emulação por CDP (`Emulation.setDeviceMetricsOverride`).
> E rode `runserver` **sem** `--noreload`: no Django 5.2 o cached loader fica
> ativo mesmo em DEBUG, e é o autoreloader que limpa o cache de templates.

---

## Testes

```bash
python manage.py test          # 45 testes
```

Cobrem: preço de assinatura, máquina de estados do pedido, baixa e devolução de
estoque, cobrança por cartão e Pix, mascaramento de dados sensíveis, validação
e reprocessamento de webhook, estorno integral e parcial, fallback de driver, e
smoke test de todas as páginas públicas, autenticadas e do painel.

---

## API

`GET /api/v1/catalogo/produtos/` — filtros: `categoria`, `marca`, `especie`,
`assinatura=1`, `promocao=1`, `destaque=1`, `search`, `ordering`.

Também: `catalogo/categorias|marcas|especies`, `carrinho/`, `pedidos/`
(autenticado), `notificacoes/`.

---

## Produção

Em ar: **https://agrocampo.online**

O host de destino já roda um Traefik (provider `file`, sem provider docker) e
outros serviços. Por isso o AgroCampo sobe como um stack Docker **isolado**,
em `/opt/agrocampo`, com rede interna, volumes e teto de CPU/RAM próprios —
uma VPS dentro do dedicado. A única ponte é o nginx de borda, o único
container que enxerga a rede do Traefik.

```bash
git clone https://github.com/kauasantossacramento/agrocampo.git /opt/agrocampo
cd /opt/agrocampo
cp .env.example .env      # preencha DJANGO_SECRET_KEY e POSTGRES_PASSWORD
docker compose up -d --build
# e publique a rota, um arquivo NOVO no dynamic do Traefik:
cp deploy/traefik-agrocampo.yml /caminho/do/traefik/dynamic/agrocampo.yml
```

| Serviço | Limite | Papel |
|---|---|---|
| `agrocampo-nginx` | 0.5 CPU / 256 MB | borda: static, media e proxy |
| `agrocampo-web` | 2 CPU / 2 GB | Gunicorn (3 workers) |
| `agrocampo-db` | 1 CPU / 1 GB | PostgreSQL 16 |
| `agrocampo-cron` | 0.5 CPU / 512 MB | assinaturas, diariamente às 6h |

O TLS termina no Traefik, que emite e renova o Let's Encrypt. Por isso o
container roda com `DJANGO_SECURE_SSL_REDIRECT=False` — se o Django também
redirecionasse, viraria laço infinito.

---

## Deploy em VPS sem Docker (Ubuntu/Debian)

Um script faz tudo: pergunta o domínio, instala as dependências do sistema,
cria o Postgres, o venv, roda as migrações, sobe o Gunicorn atrás do Nginx e
emite o certificado Let's Encrypt.

```bash
git clone git@github.com:kauasantossacramento/agrocampo.git
cd agrocampo
sudo bash deploy/install.sh
```

O script pergunta:

| Pergunta | Para que serve |
|---|---|
| Domínio | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `server_name` do Nginx e o certificado |
| E-mail do Let's Encrypt | avisos de expiração do certificado |
| Incluir `www.` | adiciona o subdomínio ao certificado |
| E-mail e senha do administrador | cria o superusuário da loja |
| Popular com demonstração | roda `seed` + `baixar_imagens` |

O que ele deixa pronto:

- `/opt/agrocampo` com venv própria e dono `agrocampo` (usuário de sistema, sem shell)
- Postgres com senha aleatória, gravada só no `.env` (modo `600`)
- `SECRET_KEY` aleatória — e **preservada** se você rodar o script de novo
- Gunicorn via socket systemd, com `ProtectSystem`/`PrivateTmp` ligados
- Nginx servindo `/static/` e `/media/` direto do disco, com gzip e cache
- HTTPS com renovação automática
- Cron diário às 6h para `processar_assinaturas`
- `/opt/agrocampo/CREDENCIAIS.txt` com o resumo (só root lê)

É **idempotente**: rodar de novo atualiza sem recriar banco nem trocar a
`SECRET_KEY`. Se o DNS ainda não propagou, ele detecta, pula o certificado e
deixa o site no ar em HTTP com o `SECURE_SSL_REDIRECT` desligado — senão o
Django redirecionaria para um HTTPS que ainda não existe.

Para atualizar depois:

```bash
sudo bash /opt/agrocampo/deploy/atualizar.sh
```

---

## Produção — checklist

- `DJANGO_DEBUG=False` e `DJANGO_SECRET_KEY` novo
- `DATABASE_URL` apontando para PostgreSQL
- `python manage.py collectstatic`
- Provedor Stone com driver `stone`, ambiente `producao` e webhook secret
- Cron diário para `processar_assinaturas`
- `EMAIL_BACKEND` SMTP real (hoje escreve no console)
