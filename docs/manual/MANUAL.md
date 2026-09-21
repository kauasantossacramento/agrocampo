# Manual do sistema — Veterinária AgroCampo

> Loja virtual em **https://agrocampo.online**. Este manual cobre tudo o que existe
> no sistema, na ordem em que as pessoas usam: a loja (cliente), o painel do
> lojista, o admin técnico, os serviços de fundo (WhatsApp, Silvinha, assinaturas)
> e a operação no servidor. Os prints estão na pasta `prints/` ao lado deste
> arquivo — sempre em duas versões quando faz diferença: **computador** e **celular**.
>
> Atualizado em 21/09/2026 (código `main`, 221 testes automatizados verdes).

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Acessos e perfis](#2-acessos-e-perfis)
3. [A loja, pelo olhar do cliente](#3-a-loja-pelo-olhar-do-cliente)
4. [Silvinha — assistente e compra pelo chat](#4-silvinha--assistente-e-compra-pelo-chat)
5. [Conta do cliente](#5-conta-do-cliente)
6. [Painel do lojista](#6-painel-do-lojista)
7. [Conteúdo da loja](#7-conteúdo-da-loja)
8. [Configurações](#8-configurações)
9. [Entrega: cidades, dias de viagem e prazo](#9-entrega-cidades-dias-de-viagem-e-prazo)
10. [Assinaturas](#10-assinaturas)
11. [WhatsApp automático](#11-whatsapp-automático)
12. [Pagamentos (Stone)](#12-pagamentos-stone)
13. [Admin técnico (Django)](#13-admin-técnico-django)
14. [Aplicativo (PWA)](#14-aplicativo-pwa)
15. [Operação no servidor](#15-operação-no-servidor)
16. [Perguntas frequentes e problemas comuns](#16-perguntas-frequentes-e-problemas-comuns)
17. [Índice dos prints](#17-índice-dos-prints)

---

## 1. Visão geral

O AgroCampo é uma loja completa para ração, saúde animal, aves e insumos rurais,
com entrega própria na região de Valença/BA. O sistema tem três camadas:

| Camada | Quem usa | Onde |
|---|---|---|
| **Loja** | clientes | `https://agrocampo.online/` |
| **Painel do lojista** | equipe da loja | `https://agrocampo.online/painel/` |
| **Admin técnico** | analista/desenvolvedor | `https://agrocampo.online/admin/` |

Serviços que rodam sozinhos: cobrança/lembrete das assinaturas (todo dia às 6h),
envio de avisos por WhatsApp (quando ligado) e a assistente Silvinha (IA do Google).

O que o lojista **nunca precisa** fazer: mexer em código, subir arquivo no servidor
ou entrar no admin técnico. Tudo do dia a dia está no painel.

---

## 2. Acessos e perfis

| Perfil | O que vê | Onde entra |
|---|---|---|
| **Cliente** | loja, carrinho, pedidos, assinaturas, endereços | `/conta/entrar/` |
| **Lojista** (operador) | tudo do cliente + **Painel** | mesmo login; o menu da conta ganha "Painel do lojista" |
| **Admin** (superusuário) | tudo do lojista + **/admin/** | mesmo login |

O login é por **e-mail e senha**. O cadastro pede nome, e-mail, **WhatsApp** (obrigatório —
é por ele que a loja fala com o cliente se faltar um item) e senha de 8+ caracteres.

- Cadastro: ![](prints/loja-cadastrar-desktop.png)
- Entrar (celular): ![](prints/loja-entrar-celular.png)

Para trocar a senha do administrador da loja: Perfil → alterar senha, ou pelo servidor
(`docker exec -it agrocampo-web python manage.py changepassword <e-mail>`).

---

## 3. A loja, pelo olhar do cliente

### 3.1 Home

A home tem o estilo **Vitrine** (padrão) — barra superior com *Rastrear meu pedido* e
*WhatsApp*, logo grande, busca larga, menu escuro com *Promoções* e *Lançamentos* em
destaque, carrossel de banners e seções divididas com título, ícone e "ver todos".
O estilo **Clássico** (o desenho anterior) continua disponível em Configurações › Aparência.

![Home no computador](prints/loja-home-desktop.png)

![Home no celular](prints/loja-home-celular.png)

**Ordem das seções** (editável em Configurações › Vitrines, com setas):
Maiores sucessos → Linha Ouro → Prata → Bronze → Navegue pelo seu animal →
Compre por categoria → Faixas de produtos → Oferta do dia → Em promoção →
Ofertas em destaque → Lançamentos → Assinatura → Por que comprar → Blog →
Newsletter → Nossas marcas. Uma seção sem conteúdo (sem produto na linha, sem
post) simplesmente não aparece.

**Carrossel**: reúne, numa fita só, os *cartazes* (Conteúdo › Banners › posição
"Carrossel principal") e os *vídeos/fotos* (posição "Vídeo ou foto de apresentação").
Cartaz com título mostra o texto sobre a imagem, entrando pela esquerda com um
gradiente escuro. Setas e pontos ficam sobre a mídia. Com um único slide não há setas.

**Promoções em destaque**: bloco vermelho com prazo (Conteúdo › Promoções), encaixado
depois da seção escolhida. Some sozinho quando vence.

### 3.2 Busca com sugestões

Ao digitar, aparecem categorias, marcas, espécies e produtos (foto, marca, preço) e o
atalho "Ver todos os resultados". Vazio, mostra "buscas populares". Setas ↑↓ e Enter
funcionam. No celular a busca fica logo abaixo do cabeçalho, com a lupa branca.

![Sugestões (computador)](prints/loja-busca-sugestoes-desktop.png)

![Sugestões (celular)](prints/loja-busca-sugestoes-celular.png)

### 3.3 Catálogo e filtros

Filtros por categoria, faixa de preço, marca, espécie, linha (Ouro/Prata/Bronze),
assinatura e promoção; ordenação por relevância, preço, novidades, mais vendidos.
No celular os filtros ficam recolhidos num botão e abrem em painel sem limite de altura.

![Catálogo](prints/loja-catalogo-desktop.png)

![Filtros no celular](prints/loja-catalogo-filtros-celular.png)

### 3.4 Página do produto

Galeria, **tamanhos** (kg/g, cada um com preço, estoque e foto próprios), quantidade,
**Adicionar ao carrinho**, **Comprar agora** (vai direto ao checkout), **calculadora de
frete e prazo** (cidade → ilha/bairro → valor, data e avisos, com a mesma regra do
checkout) e a **assinatura fechada** por padrão: "Deseja ativar a assinatura deste
produto?" abre as frequências (30/60/90 dias) e o texto de confirmação.

![Produto (computador)](prints/loja-produto-desktop.png)

![Produto (celular)](prints/loja-produto-celular.png)

### 3.5 Carrinho, entrega e pagamento

Fluxo em três passos: **carrinho** → **entrega** (endereço, avisos da cidade,
previsão de entrega, observações) → **pagamento** (Pix com desconto opcional ou
cartão em até N× sem juros — o N vem do adquirente) → **confirmação**.

Depois do pagamento o pedido **entra direto em separação** — não existe mais etapa de
aprovação. Se faltar algum item, o pedido segue e o painel marca "falar com o cliente";
o atendente combina troca ou devolução pelo WhatsApp.

![Carrinho (computador)](prints/loja-carrinho-desktop.png)
![Carrinho (celular)](prints/loja-carrinho-celular.png)
![Entrega (computador)](prints/loja-checkout-entrega-desktop.png)
![Entrega (celular)](prints/loja-checkout-entrega-celular.png)
![Pagamento (computador, cartão)](prints/loja-pagamento-desktop.png)
![Pagamento (celular, Pix)](prints/loja-pagamento-celular.png)

### 3.6 Outras páginas

- **Onde entregamos** (`/entrega/onde-entregamos/`): cidades, dias de viagem, frete,
  ilhas e avisos — tudo vindo do painel. ![](prints/loja-onde-entregamos-desktop.png)
- **Espécies** (`/especies/`) e **Marcas** (`/marcas/`): navegação por animal e por marca.
  ![](prints/loja-especies-desktop.png)
- **Blog** (`/blog/`), que pode ser desligado em Regras da loja. ![](prints/loja-blog-celular.png)
- Páginas institucionais (Quem somos, Entregas e prazos, Trocas, Privacidade, FAQ) —
  editáveis em Conteúdo › Páginas.

---

## 4. Silvinha — assistente e compra pelo chat

A Silvinha aparece na **home** e nas **páginas de produto** (canto inferior esquerdo).
Ela responde com o que está no banco: catálogo publicado (filtrado pela pergunta),
cidades atendidas e dias de viagem, frete, horário, contato. Não inventa preço nem prazo,
não dá diagnóstico veterinário e encaminha ao WhatsApp o que não sabe. A conversa
sobrevive à navegação entre páginas.

**Compra pelo chat.** Quando o cliente diz que quer comprar algo, a Silvinha confirma o
produto e a quantidade e um **cartão de compra** aparece na conversa (foto, preço,
tamanho, quantidade, opção de assinatura quando o produto permite). Ao tocar em
*Comprar agora*:

- se a pessoa **já está logada**: o item vai para o carrinho e ela é levada à entrega/pagamento;
- se **não está**: o próprio chat pede **e-mail e senha** ou cria a conta (**nome, e-mail,
  WhatsApp, senha**), entra automaticamente, junta o carrinho anônimo e segue para o pagamento.

A IA só *propõe*; quem confirma é sempre o botão do cliente.

![Silvinha propondo a compra e pedindo o cadastro (computador)](prints/loja-silvinha-compra-desktop.png)

![Silvinha no celular](prints/loja-silvinha-compra-celular.png)

**Configuração** (Configurações › Silvinha): interruptor, nome, foto/avatar, primeira
mensagem, orientações extras (ex.: "não prometa prazo fora da lista"), **chave do Gemini**
e modelo (`gemini-3.6-flash`). Sem chave ela ainda aparece, mas só encaminha ao WhatsApp.
Limite de 40 perguntas por hora por pessoa. As últimas conversas aparecem na mesma aba.

![](prints/painel-config-silvinha-desktop.png)

---

## 5. Conta do cliente

- **Meus pedidos** com linha do tempo (pago → separação → saiu para entrega → entregue),
  botão de pagar quando aguardando pagamento. ![](prints/loja-meus-pedidos-desktop.png)
  ![](prints/loja-pedido-detalhe-celular.png)
- **Minhas assinaturas**: pausar, cancelar, pular ciclo, ver próxima data. ![](prints/loja-assinaturas-desktop.png)
- **Meus dados** e **Endereços** (com cidade atendida e ilha/bairro, que definem frete e prazo).
  ![](prints/loja-conta-perfil-desktop.png) ![](prints/loja-conta-enderecos-celular.png)
- **Notificações** no sino do cabeçalho; no celular abrem em folha rolável. ![](prints/loja-notificacoes-celular.png)
- **Lista de desejos** (coração no cabeçalho; no celular, pelo menu lateral).

---

## 6. Painel do lojista

Entre em `/painel/` (menu da conta → *Painel do lojista*). O menu lateral tem:
Pedidos, Métricas, Produtos, Estoque, Assinaturas, Conteúdo, Entrega, Itinerário,
Auditoria, Configurações. O sino mostra os avisos da equipe (pedido novo, falar com o
cliente, estoque baixo).

### 6.1 Pedidos

Lista com busca, filtro por status e os números do dia. Cada pedido abre com itens,
pagamento, linha do tempo, endereço e as ações: **marcar como enviado** (com rastreio
opcional), **Chamar no WhatsApp** (abre a conversa com o texto do pedido pronto) e,
para pedidos antigos, aprovar/recusar.

![Pedidos](prints/painel-pedidos-desktop.png)
![Pedidos no celular](prints/painel-pedidos-celular.png)
![Detalhe do pedido](prints/painel-pedido-detalhe-desktop.png)

Pedido marcado com **"falar com o cliente"** = algum item saiu sem estoque suficiente na
separação. O que existia foi baixado; o atendente combina o resto.

### 6.2 Itinerário de entrega

A folha do entregador: pedidos em separação (ou já na rua) agrupados por
**cidade → ilha/localidade → bairro**, ordenados pela rua, com quem recebe, telefone,
endereço, referência, itens e valor. Filtros por status, cidade e "pagos até" uma data.
**Imprimir** gera a versão A4 sem a moldura do painel.

![Itinerário](prints/painel-itinerario-desktop.png)
![Itinerário no celular](prints/painel-itinerario-celular.png)

### 6.3 Produtos

Lista com **edição rápida** em linha (preço, estoque, no ar, **Sucesso**) e o botão de
lápis que abre o cadastro completo em modal: nome, categoria, marca, **linha
(Ouro/Prata/Bronze)**, preços, promoção com prazo, estoque, unidade, peso,
**tamanhos** (kg/g com preço/estoque/foto), assinatura, fotos, benefícios,
"Maior sucesso", lançamento, publicado. O SKU é opcional (gerado).

![Produtos](prints/painel-produtos-desktop.png)
![Cadastro de produto](prints/painel-produto-editar-desktop.png)
![Produtos no celular](prints/painel-produtos-celular.png)

**Maiores sucessos** é manual: por produto (caixa "Maior sucesso"), em lote na coluna
*Sucesso* da lista, ou **marca inteira** (Conteúdo › Marcas › "todos os produtos desta
marca em Maiores sucessos").

### 6.4 Estoque, Métricas, Assinaturas, Auditoria

- **Estoque**: itens abaixo do mínimo, reposição com um clique e histórico de movimentos. ![](prints/painel-estoque-desktop.png)
- **Métricas**: vendas por período, ticket médio, assinaturas ativas, mais vendidos. ![](prints/painel-metricas-desktop.png)
- **Assinaturas**: todas as assinaturas, status, próxima data, ciclos cobrados/lembrados. ![](prints/painel-assinaturas-desktop.png)
- **Auditoria**: trilha bruta de pagamentos, webhooks e estornos — para conferir com a Stone. ![](prints/painel-auditoria-desktop.png)

---

## 7. Conteúdo da loja

Menu **Conteúdo** (e **Entrega**, que é o grupo de entrega do mesmo lugar). Cada tela é
uma lista com busca e o botão "Novo…" que abre o formulário em modal.

| Tela | Para quê |
|---|---|
| **Banners** | os slides do carrossel (*Carrossel principal* = cartaz 16:5 com link, título opcional; *Vídeo ou foto de apresentação* = mídia grande, entra no mesmo carrossel), as **Ofertas em destaque** (*Oferta em destaque (cartaz na home)* — 1 ocupa a largura toda, 2 lado a lado, 3+ em duas colunas; liga/desliga por *publicado*) e a *Faixa de produtos* (fotos de produtos com link). |
| **Promoções em destaque** | bloco com título, texto, imagem ou produto, **início e fim** e a seção depois da qual entra. |
| **Faixa de garantias** | os quatro selos abaixo do carrossel (frete, Pix, assinatura, compra garantida). |
| **Páginas institucionais** | Quem somos, Entregas e prazos, Trocas, Privacidade, FAQ (HTML simples). |
| **Categorias / Marcas / Espécies** | a árvore do catálogo; marca tem o atalho de "Maiores sucessos"; espécie tem foto e destaque na home. |
| **Cupons** | código, percentual/valor, validade, mínimo. |
| **Cidades atendidas / Ilhas e localidades / Avisos de entrega** | ver a seção 9. |

![Banners](prints/painel-conteudo-banners-desktop.png)
![Formulário de banner](prints/painel-conteudo-banner-form-desktop.png)
![Promoções em destaque](prints/painel-conteudo-promocoes-desktop.png)
![Marcas](prints/painel-conteudo-marcas-desktop.png)
![Cupons](prints/painel-conteudo-cupons-desktop.png)
![Conteúdo no celular](prints/painel-conteudo-celular.png)

---

## 8. Configurações

`/painel/configuracoes/`, em abas:

| Aba | O que tem |
|---|---|
| **Aparência** | nome, frase e descrição da capa; **estilo da home** (Vitrine/Clássico); **interruptores da capa** (carrossel de slides; bloco de apresentação separado, desligado por padrão); logo (até 120 px de altura), logo para fundo escuro, ícone, imagem de capa; faixa do topo. ![](prints/painel-config-aparencia-desktop.png) |
| **Pagamentos** | credenciais da Stone (API Key, Merchant ID, webhook secret, chave Pix…), driver (Stone/Simulado), ambiente, parcelas sem juros. ![](prints/painel-config-pagamentos-desktop.png) |
| **Regras da loja** | frete global (para cidade não cadastrada), frete grátis acima de, **desconto da assinatura (padrão 0)**, **mostrar a assinatura na loja**, desconto no Pix, blog ligado. ![](prints/painel-config-regras-desktop.png) |
| **Entrega** | entregas a partir de (hora), **pedidos até (hora de corte)**, aviso geral, balão do WhatsApp e mensagem. ![](prints/painel-config-entrega-desktop.png) |
| **Vitrines** | título e interruptor de cada linha (Ouro/Prata/Bronze) e a **ordem das seções da home**. ![](prints/painel-config-vitrines-desktop.png) |
| **Contato** | telefone, WhatsApp, e-mail, endereço, horário, CNPJ, redes, ano de fundação, texto do rodapé. ![](prints/painel-config-contato-desktop.png) |
| **WhatsApp** | interruptor do envio automático, sessão (QR Code), teste, últimas mensagens — ver seção 11. ![](prints/painel-config-whatsapp-desktop.png) |
| **Silvinha** | ver seção 4. |
| **Notificações** | Firebase (push para o app), opcional. ![](prints/painel-config-notificacoes-desktop.png) |
| **Avançado** | atalhos para todo o conteúdo, limpar catálogo de demonstração. ![](prints/painel-config-avancado-desktop.png) |

![Configurações no celular](prints/painel-config-celular.png)

---

## 9. Entrega: cidades, dias de viagem e prazo

A loja entrega numa região concreta, não no Brasil inteiro. Em vez de adivinhar por CEP,
o lojista cadastra:

- **Cidades atendidas** (Entrega › Cidades): frete, *frete grátis acima de* (vazio usa o
  global; 0 desliga), **dias de viagem** (os dias em que o carro vai — ex.: só sexta),
  **antecedência** (0 = sai no mesmo dia se o pedido entrar antes da hora de corte),
  horário próprio, observação mostrada no checkout, *cidade sede*.
- **Ilhas e localidades**: bairro, povoado ou ilha com **acréscimo** (ex.: R$ 10 na travessia)
  e dias extras.
- **Avisos de entrega**: recados por momento (carrinho, endereço, pagamento, depois de
  finalizar), com destaque em amarelo.

![Cidades](prints/painel-conteudo-cidades-desktop.png)
![Ilhas e localidades](prints/painel-conteudo-localidades-desktop.png)
![Avisos de entrega](prints/painel-conteudo-avisos-desktop.png)

**Como a data de entrega é calculada** (checkout, calculadora do produto e Silvinha
usam a mesma regra):

1. Pedido depois da **hora de corte** (Configurações › Entrega, padrão 14h) conta como do dia seguinte.
2. Soma-se a **antecedência** da cidade.
3. A data cai no **próximo dia de viagem** da cidade. Cidade sem dias marcados = dias úteis.
4. Ilha/localidade soma os dias extras.

Exemplo em produção: **Valença/BA** = sede, frete grátis, viagem **só às sextas**,
antecedência 0. Pedido na segunda → entrega na sexta da mesma semana.

Endereço em cidade **não cadastrada**: o frete cai no valor global e o checkout avisa
que a loja confirma a entrega pelo WhatsApp.

---

## 10. Assinaturas

O cliente liga a assinatura na página do produto (30, 60 ou 90 dias). Quando o primeiro
pedido é pago, nasce a **assinatura** com a próxima data marcada. Todo dia às 6h o
sistema (`processar_assinaturas`) faz três coisas:

| Situação | O que acontece |
|---|---|
| **2 dias antes** da data | aviso "Sua assinatura renova em 2 dias" (in-app, e-mail e WhatsApp se ligado), uma vez só. |
| Na data, **com cartão salvo** | cobra automaticamente, cria o pedido já em separação, avisa "Assinatura renovada". Recusa: tenta de novo em 3 dias; 3 falhas seguidas cancelam. |
| Na data, **sem cartão** (ex.: pagou no Pix) | **modo lembrete**: cria o pedido *aguardando pagamento* e avisa "Hora de renovar sua assinatura" com o link para pagar. Não conta como falha. |

O desconto da assinatura é **0% por padrão** (Regras da loja); a assinatura vira só
comodidade de entrega. Há um interruptor para esconder a assinatura da loja inteira.
Tudo isso tem teste automatizado (`apps/subscriptions/tests.py`).

---

## 11. WhatsApp automático

Dois caminhos convivem:

- **Manual (sempre disponível)**: balão flutuante na loja e o botão *Chamar no WhatsApp*
  no pedido, que abrem a conversa com o texto pronto (`wa.me`).
- **Automático (interruptor)**: um serviço no servidor mantém uma sessão do **WhatsApp
  Web** e envia sozinho *pedido confirmado*, *item em falta — vamos falar com você*,
  *saiu para entrega*, *renovação da assinatura* e o *aviso prévio*. Só para clientes
  que autorizaram contato no cadastro.

> **Risco que o lojista assumiu:** o automático **não é a API oficial da Meta**. Controlar
> o WhatsApp Web por robô viola os Termos de Serviço e o número pareado **pode ser
> banido sem aviso**. Use um chip dedicado à loja, nunca o número principal.

**Para ligar**: Configurações › WhatsApp → ler o **QR Code** com o celular da loja
(WhatsApp › Aparelhos conectados) → esperar "Conectado" → *Enviar teste* → marcar
*Enviar os avisos automaticamente* → Salvar. A aba mostra as últimas mensagens e o
motivo de cada falha. *Desconectar este número* encerra a sessão.

Detalhes técnicos em `deploy/whatsapp/README.md` e `docs/WHATSAPP-NOTIFICACOES.md`
(que também documenta a API oficial, para quando o volume justificar).

---

## 12. Pagamentos (Stone)

O adquirente é configurado **pelo painel** (Configurações › Pagamentos), não por deploy.
Enquanto o driver estiver em **Simulado**, a loja aceita pedidos mas **não movimenta
dinheiro** (cartão terminado em 0000 é recusado; Pix é confirmado por um botão de
simulação). Com as credenciais da Stone e o driver em *Stone*, cadastre o webhook
`https://agrocampo.online/pagamentos/webhook/stone/` no painel da Stone.

Dados de cartão nunca são guardados: só bandeira, 4 últimos dígitos e o *token* que a
Stone devolve (é ele que permite a cobrança automática da assinatura).

---

## 13. Admin técnico (Django)

`/admin/` é a ferramenta do analista: acesso cru a todas as tabelas (usuários, pedidos,
pagamentos, webhooks, conversas da Silvinha, mensagens de WhatsApp…). O lojista não
precisa dele; tudo do dia a dia está no painel.

![Admin](prints/admin-django-desktop.png)
![Admin — produtos](prints/admin-django-produtos-desktop.png)

---

## 14. Aplicativo (PWA)

A loja pode ser **instalada** no celular (o convite aparece depois de alguns segundos de
navegação; o tempo e o texto são configuráveis em Aparência). O ícone é vermelho com a
logo branca. Um app já instalado só troca o ícone ao reinstalar. Notificações push
dependem do Firebase (aba Notificações), opcional.

---

## 15. Operação no servidor

Resumo — o detalhe completo, com o que foi feito em cada entrega e como reverter, está
em `deploy/RELATORIO-SERVIDOR.md`; os dados de acesso, em `deploy/DADOS-DE-DEPLOY.md`
(fora do Git).

- Servidor dedicado (nuvem.center), app em `/opt/agrocampo` como stack Docker isolado:
  `web` (Django), `db` (Postgres), `nginx`, `cron` (assinaturas 6h), `whatsapp` (sessão do WhatsApp Web).
- **Atualizar**: backup → `git pull --ff-only` → `docker compose build web` →
  `docker compose run --rm --no-deps web python manage.py migrate` →
  `docker compose up -d --no-deps web`. Nunca `up -d` sem `--no-deps` (recria o banco).
- Backups do banco ficam em `/root/backup-agrocampo-*.sql.gz`.
- Regra dura: **nada fora de `/opt/agrocampo`** — o host serve outros sistemas.
- Testes: `python manage.py test` (221 testes).

---

## 16. Perguntas frequentes e problemas comuns

**A home está sem o carrossel.** Aparência › *mostrar o carrossel de slides* ligado, e
pelo menos um banner *publicado* nas posições "Carrossel principal" ou "Vídeo ou foto de
apresentação". Sem nenhum, entra o slide de texto vermelho de reserva.

**Uma seção sumiu da home.** Ela só aparece com conteúdo (produto na linha, promoção no
prazo, post no blog). Confira também a ordem em Vitrines.

**O frete/prazo não aparece na página do produto.** Não há cidade cadastrada em
Entrega › Cidades atendidas.

**A Silvinha só manda para o WhatsApp.** Falta a chave do Gemini (Configurações ›
Silvinha) ou o modelo está errado (use `gemini-3.6-flash`).

**WhatsApp automático "Serviço não configurado".** Falta `WHATSAPP_WEB_TOKEN` no `.env`
do servidor. "Aguardando QR": leia o QR na aba. "Erro/indisponível": o WhatsApp mudou o
protocolo — atualizar o serviço (`deploy/whatsapp/README.md`).

**O ícone do app continua antigo.** Reinstale o app no celular.

**Quero voltar o visual antigo.** Aparência › Estilo da home → Clássico. Nada se perde.

**Pedido com "falar com o cliente".** Faltou estoque de um item na separação. Use
*Chamar no WhatsApp* no pedido para combinar troca ou devolução.

---

## 17. Índice dos prints

| Arquivo | O que mostra |
|---|---|
| `loja-home-desktop.png` / `loja-home-celular.png` | home completa |
| `loja-busca-sugestoes-*.png` | busca com sugestões ao digitar |
| `loja-catalogo-desktop.png` / `loja-catalogo-filtros-celular.png` | catálogo e filtros |
| `loja-produto-*.png` | produto com assinatura aberta e frete calculado |
| `loja-silvinha-compra-*.png` | Silvinha propondo compra e pedindo acesso |
| `loja-carrinho-*.png`, `loja-checkout-entrega-*.png`, `loja-pagamento-*.png` | compra em três passos |
| `loja-meus-pedidos-desktop.png`, `loja-pedido-detalhe-celular.png` | pedidos do cliente |
| `loja-assinaturas-desktop.png` | assinaturas do cliente |
| `loja-notificacoes-celular.png` | sino de notificações no celular |
| `loja-conta-perfil-desktop.png`, `loja-conta-enderecos-celular.png` | dados e endereços |
| `loja-entrar-celular.png`, `loja-cadastrar-desktop.png` | login e cadastro |
| `loja-onde-entregamos-desktop.png`, `loja-especies-desktop.png`, `loja-blog-celular.png` | páginas públicas |
| `painel-pedidos-*.png`, `painel-pedido-detalhe-desktop.png` | pedidos no painel |
| `painel-itinerario-*.png` | itinerário de entrega |
| `painel-produtos-*.png`, `painel-produto-editar-desktop.png` | produtos e cadastro |
| `painel-estoque-desktop.png`, `painel-metricas-desktop.png`, `painel-assinaturas-desktop.png`, `painel-auditoria-desktop.png` | demais telas do painel |
| `painel-conteudo-*.png` | banners, promoções, cidades, localidades, avisos, marcas, cupons |
| `painel-config-*.png` | cada aba de Configurações |
| `admin-django-*.png` | admin técnico |
