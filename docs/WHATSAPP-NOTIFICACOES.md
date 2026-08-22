# Notificação por WhatsApp após a compra

**Status:** avaliação técnica. Nada foi ligado em produção.
**Data:** 22/08/2026
**Para:** decisão do lojista sobre qual caminho seguir.

---

## O que a loja quer

Quando o cliente termina a compra, ele deve receber uma mensagem no WhatsApp
com o número do pedido e o andamento. E quando falta um item, um atendente
precisa chamar esse cliente para combinar a troca — hoje isso só existe como
alerta dentro do painel.

## Resumo da recomendação

**Comece pelo caminho 1 (link `wa.me` com mensagem pronta), que já está
implementado e custa zero. Se o volume crescer, vá para o caminho 3 (API
oficial da Meta), não para o 2.**

O caminho 2 (WhatsApp Web automatizado) é o mais tentador porque parece
grátis e automático, mas ele viola os Termos de Serviço do WhatsApp e o
número da loja pode ser banido — inclusive o número que os clientes já
conhecem. Não vale o risco para uma loja cujo WhatsApp *é* o canal de vendas.

---

## Os três caminhos, comparados

| | 1. Link `wa.me` | 2. WhatsApp Web (não oficial) | 3. API Oficial (Cloud API) |
|---|---|---|---|
| **Custo** | R$ 0 | R$ 0 em software, mas exige um servidor rodando 24h | Grátis até 1.000 conversas/mês de serviço; depois ~R$ 0,08 por conversa iniciada pela loja |
| **Automático?** | Não — alguém clica | Sim | Sim |
| **Risco de banimento** | Nenhum | **Alto** — viola os Termos | Nenhum |
| **Precisa de aprovação da Meta** | Não | Não | Sim (verificação da empresa + modelos de mensagem) |
| **Prazo para funcionar** | Já funciona | 1–2 dias de desenvolvimento | 1–3 semanas (a verificação da Meta é a parte lenta) |
| **Número usado** | O da loja | O da loja (com risco) | Um número dedicado, que **não pode** estar em uso no app comum |
| **Estabilidade** | Total | Quebra a cada atualização do WhatsApp | Contrato estável |

---

## Caminho 1 — Link `wa.me` (implementado, funcionando)

É o que está no ar hoje. O sistema não envia nada sozinho; ele deixa a
conversa pronta a um toque.

**O que já existe no código:**

- Balão flutuante do WhatsApp em todas as páginas
  (`templates/partials/whatsapp_balao.html`), com número e mensagem
  configuráveis em **Painel → Configurações → Entrega**.
- WhatsApp obrigatório no cadastro do cliente, com caixa de consentimento
  (`apps/accounts/forms.py`, `CadastroForm`).
- `User.whatsapp_url` — monta o link `wa.me` do cliente já com o DDI 55.
  Devolve vazio se o cliente não autorizou contato.
- Quando falta estoque, o pedido segue para separação e marca
  `Pedido.contato_pendente` + `Pedido.itens_em_falta`, e o lojista recebe uma
  notificação no painel (`apps/orders/services.py`, `separar_pedido`).
- Botão **Chamar no WhatsApp** na tela do pedido, no painel, que abre a
  conversa com o cliente já com o texto do pedido preenchido.

**Limite honesto:** depende de alguém da loja clicar. Para o volume atual
provavelmente basta; para 50 pedidos por dia, não.

---

## Caminho 2 — WhatsApp Web automatizado (**não recomendado**)

Bibliotecas como `whatsapp-web.js`, `Baileys` e `venom-bot` controlam uma
sessão do WhatsApp Web e conseguem disparar mensagens sozinhas. Rodam num
Node.js separado, que o Django chamaria por HTTP.

**Por que não recomendo, apesar de ser "grátis":**

1. **Viola os Termos de Serviço do WhatsApp.** A Meta bane números que
   detecta usando clientes não oficiais. O número banido é justamente o que
   está impresso nos cartões da loja e que os clientes já salvaram.
2. **Quebra sozinho.** A sessão cai quando o WhatsApp atualiza o protocolo, e
   o celular precisa reconectar lendo um QR Code. Na prática, alguém tem que
   vigiar isso toda semana.
3. **Precisa de um servidor extra rodando 24h** com a sessão viva — ou seja,
   não é realmente de graça: é mais um container, mais memória, mais uma
   coisa que pode cair de madrugada.

**Se mesmo assim o lojista quiser seguir por aqui**, o que falta é: um
serviço Node com `whatsapp-web.js`, um endpoint interno protegido por token,
volume persistente para a sessão, e um gancho no Django chamando esse
endpoint quando o pedido muda de status. Posso construir sob pedido — mas
registro aqui que o risco recai sobre o número da loja.

---

## Caminho 3 — API Oficial da Meta (Cloud API)

É o caminho oficial e é o que eu recomendaria assim que o volume justificar.

**Custo real:** a Meta cobra por *conversa*, não por mensagem. Conversas de
"serviço" (respostas a algo que o cliente iniciou) e as primeiras 1.000 por
mês são gratuitas. Mensagens que a loja inicia — como "seu pedido saiu para
entrega" — entram na categoria "utilidade", hoje em torno de **R$ 0,08 por
conversa de 24 horas** no Brasil. Cem pedidos por mês ficam abaixo de R$ 10.

> Os valores acima mudam com a tabela da Meta. Confirme em
> `developers.facebook.com/docs/whatsapp/pricing` antes de fechar conta.

**O que a Meta exige antes de liberar:**

- Conta no Meta Business Manager com a empresa **verificada** (CNPJ,
  comprovante de endereço). É a etapa mais lenta — leva de dias a semanas.
- Um **número de telefone dedicado**, que não esteja registrado no app comum
  do WhatsApp nem no WhatsApp Business. Se a loja usar o número atual, perde
  o app no celular.
- **Modelos de mensagem aprovados** previamente. Não dá para escrever texto
  livre para quem não falou com a loja nas últimas 24 horas.

### O que eu preciso receber do lojista para implementar

Sem estes cinco itens não é possível ligar nada — não há como contornar:

| # | Item | Onde consegue |
|---|---|---|
| 1 | `WHATSAPP_PHONE_NUMBER_ID` | Meta Business → WhatsApp → Configuração da API |
| 2 | `WHATSAPP_BUSINESS_ACCOUNT_ID` | mesma tela |
| 3 | Token permanente de acesso | Meta Business → Usuários do sistema → gerar token |
| 4 | Número dedicado, já verificado | um chip novo, **fora** do app do WhatsApp |
| 5 | Modelos de mensagem aprovados | Meta Business → Modelos de mensagem |

### Modelos que sugiro cadastrar

No formato que a Meta pede, com as variáveis numeradas:

**`pedido_confirmado` (categoria: Utilidade)**
> Olá, {{1}}! Recebemos o seu pedido {{2}} na AgroCampo. Total: R$ {{3}}.
> Acompanhe por aqui: {{4}}

**`pedido_a_caminho` (categoria: Utilidade)**
> {{1}}, seu pedido {{2}} saiu para entrega e chega hoje a partir das {{3}}.

**`item_em_falta` (categoria: Utilidade)**
> Olá, {{1}}. Sobre o pedido {{2}}: o item {{3}} está em falta. Podemos
> trocar por outro ou devolver o valor — responda por aqui que a gente
> resolve.

### O que já está pronto no sistema para receber isso

O trabalho de integração fica pequeno porque a estrutura já existe:

- **Onde guardar as credenciais:** `SiteConfig` já é o lugar onde ficam as
  chaves do Firebase, no mesmo padrão (campos no banco, editáveis no painel,
  sem precisar de deploy). Os campos do WhatsApp entram do lado.
- **Onde disparar:** `apps/orders/models.py`, método `mudar_status()`, é o
  único ponto por onde todo pedido passa ao mudar de estado. Um gancho ali
  cobre todos os avisos.
- **Onde registrar:** o app `notifications` já tem `Notificacao` e o padrão de
  `notificar(...)` com envio por e-mail. O WhatsApp vira mais um canal do
  mesmo serviço, não um sistema paralelo.
- **Consentimento:** `User.aceita_contato_whatsapp` já existe e já é
  respeitado por `User.whatsapp_url`.

**Estimativa depois que as credenciais chegarem:** 1 a 2 dias de trabalho.

---

## Recomendação final

1. **Agora:** ficar no caminho 1, que já está no ar e resolve o caso mais
   urgente — falar com o cliente quando falta um item.
2. **Quando o lojista quiser automatizar:** abrir a conta no Meta Business e
   iniciar a verificação do CNPJ, porque essa espera é o gargalo. Enquanto ela
   corre, eu deixo o código pronto e desligado.
3. **Não usar o caminho 2.** O risco recai sobre o número que é o principal
   canal de venda da loja.
