# AgroCampo — Roadmap de Desenvolvimento

E-commerce completo para a **Veterinária AgroCampo**: ração, saúde animal, aves,
insumos rurais e **assinatura recorrente**, com **gateway de pagamento próprio
conectado à Stone**.

- **Backend:** Django 5 + Django REST Framework
- **Frontend:** Django Templates server-rendered + design system próprio
  (CSS custom properties, animações CSS/IntersectionObserver, JS vanilla).
  A camada DRF existe em paralelo para alimentar o PWA/app mobile.
- **Referências:** mockup `mockup/AgroCampo Mockup.dc.html` (identidade, fluxos,
  telas) + `terradospassaros.com` (profundidade de catálogo, navegação por
  espécie/marca, blocos da home, institucional).

---

## Identidade visual (extraída do mockup)

| Token | Valor | Uso |
|---|---|---|
| `--brand-red` | `#D62B20` | ação primária, destaque |
| `--brand-red-dark` | `#A81F17` | hover, estados pressionados |
| `--brand-yellow` | `#FFC72C` | acento, selos, CTA secundário |
| `--ink` | `#221812` | texto forte, footer, admin |
| `--ink-soft` | `#3A2E24` / `#4A3D33` | corpo de texto |
| `--muted` | `#8A7C70` | texto auxiliar |
| `--cream` | `#FFF8F0` | fundo da página |
| `--cream-warm` | `#FFF1E4` | superfícies e chips |
| `--green` | `#2F9E44` | sucesso, economia, estoque |
| Tipografia | Poppins 600–800 (títulos) · Inter 400–700 (texto) | |

---

## Fases

> Todas as fases abaixo foram executadas. `python manage.py test` roda 42 testes
> verdes; o storefront, o checkout, o painel do lojista e a API estão de pé.

### ✅ Fase 0 — Fundação
Estrutura do projeto, settings por ambiente via `.env`, apps registrados,
modelos-base abstratos (`TimeStamped`, `Sluggable`), storage de mídia,
whitenoise, requirements.

### ✅ Fase 1 — Design System
`design-system.css` com tokens, escala tipográfica, grid, botões, cards,
chips, badges, inputs, skeletons; `motion.css` com curvas de easing,
reveal-on-scroll, hover lifts, transições de página; `app.js` com
IntersectionObserver, carrosséis, drawers, toasts. Layout base + header
sticky + mega-menu + footer.

### ✅ Fase 2 — Catálogo (dados)
`Category` (hierárquica, MPTT-like via self-FK), `Brand`, `Species`
(navegação por espécie, à la Terra dos Pássaros), `Product`,
`ProductImage`, `ProductVariant`, `StockMovement`, `Review`.
Preço, preço promocional, preço de assinatura, flags de destaque.
Admin Django completo.

### ✅ Fase 3 — Storefront
Home (hero, faixa de garantias, categorias, mais vendidos, ofertas com
contador, navegação por espécie, marcas, blog, newsletter), catálogo com
filtros facetados (categoria, marca, espécie, preço, assinatura), busca,
página de produto (galeria, seletor de frequência, avaliações, relacionados).

### ✅ Fase 4 — Contas e Carrinho
`User` customizado (e-mail como login, CPF, telefone), `Address` com CEP,
`Cart`/`CartItem` com sessão anônima + merge no login, wishlist.

### ✅ Fase 5 — Pagamentos Stone  ⭐
Camada de gateway plugável. `PaymentProvider` guarda **as credenciais da
Stone no banco** (client_id, secret, api_key, merchant/affiliation code,
webhook secret, chave Pix, ambiente sandbox/produção). `Payment`,
`PaymentTransaction`, `PaymentWebhookEvent`, `Refund`. Driver
`StoneGateway` (cartão, Pix, boleto, estorno, tokenização) + driver
`SandboxGateway` para desenvolvimento. Endpoint de webhook assinado.

### ✅ Fase 6 — Pedidos e aprovação do lojista
`Order` com máquina de estados (aguardando pagamento → pago → aguardando
aprovação → aprovado → em separação → enviado → entregue / recusado /
estornado), `OrderItem`, `OrderEvent` (timeline), fluxo de recusa por falta
de estoque com sugestões de similares e estorno.

### ✅ Fase 7 — Assinaturas recorrentes
`SubscriptionPlan` (30/60/90 dias), `Subscription`, `SubscriptionCycle`,
geração automática de pedidos, cobrança recorrente via Stone com cartão
tokenizado, pausar/cancelar/pular ciclo.

### ✅ Fase 8 — Notificações
`Notification` (in-app), `NotificationTemplate`, canais e-mail/WhatsApp
plugáveis, sinos no header web e no painel do lojista.

### ✅ Fase 9 — Painel do lojista
Dashboard com métricas (vendas do dia, pendentes, ticket médio, assinaturas
ativas), fila de aprovação de pedidos, controle de estoque com alerta,
gestão de assinaturas, configuração da Stone.

### ✅ Fase 10 — Conteúdo institucional
Páginas CMS (Quem somos, Trocas e devoluções, Privacidade, Entregas e
prazos, FAQ), Blog com posts e categorias, Newsletter.

### ✅ Fase 11 — PWA e API
`manifest.json`, service worker, ícones, telas responsivas do app;
API DRF versionada para catálogo, carrinho, pedidos e notificações.

### ✅ Fase 12 — Dados de exemplo, testes e documentação
Seed com o catálogo do mockup, testes das regras críticas (preço de
assinatura, máquina de estados do pedido, webhook Stone), README de
operação.
