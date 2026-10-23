# Transição de agente — AgroCampo

Documento de passagem de bastão. Escrito para o **próximo agente de IA** que
pegar este projeto no meio, sem o histórico da conversa anterior. Leia inteiro
antes do primeiro comando: metade do que está aqui é coisa que já deu errado
uma vez.

> **Para o agente que assume:** o que o usuário mais valoriza é ver a mudança
> no ar. Ele acompanha pelo celular, em produção, e cobra o resultado — não o
> plano. Entregue em pedaços publicados, não em lotes grandes.

Última atualização: **10/10/2026**, commit `fc75759` + modal estático.

---

## 1. O que é

Loja virtual da **Veterinária AgroCampo**, de Valença/BA — ração, saúde animal,
aves e insumos rurais. No ar em **https://agrocampo.online**.

- **Django 5.2 + DRF**, templates renderizados no servidor.
- Design system próprio em CSS puro (tokens), JS sem framework.
- Dono do negócio: o lojista. Quem fala com você: **Kauã (KS TEC)**, o
  desenvolvedor que atende a loja.

O público do código é o lojista: ele cadastra produto **no balcão, pelo
celular**, muitas vezes com a mão ocupada. Isso explica quase toda decisão de
interface deste projeto.

---

## 2. Como rodar

```bash
cd "C:/Users/KS TEC/Downloads/agrocampo_zip2/agrocampo"
. .venv/Scripts/activate          # Windows + Git Bash
python manage.py runserver 127.0.0.1:8765 --noreload
python manage.py test             # ~300 testes, 6 a 10 minutos
```

**Armadilha nº 1 do projeto:** com `--noreload`, o servidor **guarda template,
view e templatetag em memória**. Mudou `.py` ou `.html`? **Reinicie o
servidor**, senão você vai depurar um bug que já corrigiu. (CSS e JS são
servidos do disco e não precisam de reinício — mas o navegador cacheia; veja a
seção 7.)

---

## 3. Produção

| Item | Valor |
|---|---|
| Servidor | `ssh -i deploy/chaves/nuvem-center-prod root@65.108.46.17` |
| App | `/opt/agrocampo` (stack Docker isolado) |
| Containers | `agrocampo-web`, `-db`, `-nginx`, `-cron`, `-whatsapp` |
| Entrada | Traefik externo, via **um** arquivo: `agrocampo.yml` |
| Backups | `/root/backups-agrocampo/` |

### Regra dura

> **Nada fora de `/opt/agrocampo` pode ser alterado.**

O mesmo host serve **clientes Nextcloud em produção** (stack `nuvem-*`).
Mexer fora do diretório do AgroCampo é risco para terceiros. Está registrado em
`deploy/RELATORIO-SERVIDOR.md`.

### Procedimento de deploy (funcionou em todas as entregas)

```bash
# 1. backup primeiro, sempre
docker compose exec -T db pg_dump -U agrocampo agrocampo \
  | gzip > /root/backups-agrocampo/pre-<commit>-$(date +%Y%m%d-%H%M).sql.gz
# 2. código
git pull --ff-only
docker compose build web
# 3. banco (o entrypoint também migra, mas rodar explícito deixa o log claro)
docker compose run --rm --no-deps web python manage.py migrate
# 4. subir
docker compose up -d --no-deps web
```

- **Nunca** `docker compose up -d` sem `--no-deps` — recria o banco.
- `nginx` só precisa de `--force-recreate` se `deploy/nginx.conf` mudou
  (bind mount de arquivo único não enxerga o inode novo).
- Registre cada entrega em `deploy/RELATORIO-SERVIDOR.md`, seção 10.x.

---

## 4. Convenções que o usuário cobra

1. **Português do Brasil em tudo**: nome de variável, função, model, campo,
   commit, comentário. Código em inglês destoa do resto e ele nota.
2. **Comentário explica *por que*, não *o quê*.** O padrão do projeto é
   registrar a decisão e o problema que ela resolve. Comentário que narra a
   linha seguinte é ruído.
3. **Mensagem de commit em prosa**, explicando a causa do problema, não só o
   efeito. Veja `git log` — siga o tom.
4. **Nada de lista fechada no cadastro.** Marca, categoria, linha, animal e
   unidade são campos digitados que criam o que falta. Se você adicionar um
   campo novo ao cadastro de produto, ele **tem** que seguir esse padrão
   (`campo_livre()` em `apps/dashboard/forms.py`).
5. **Toda mudança de comportamento em dados existentes precisa de `RunPython`**
   com função de volta (reversível).
6. **Teste junto.** A suíte tem ~300 testes e passa; não quebre.
7. **O admin do Django não existe para o lojista.** Fica em
   `settings.ADMIN_PATH` (padrão `dev-admin/`), restrito a `User.desenvolvedor`.
   Qualquer tela que o lojista precise ver tem que ser nativa do painel.
8. Mensagem técnica para o lojista é proibida. O padrão acordado é
   *"entre em contato com o suporte KS TEC para ativar a funcionalidade"*.

---

## 5. Mapa rápido do código

```
apps/
  catalog/     Produto, Categoria, Marca, Especie, LinhaProduto, variações
  core/        SiteConfig (singleton), Banner, PromocaoDestaque, home
  dashboard/   painel do lojista (views, forms, gestao.py = CRUD genérico)
  orders/      pedido, separação, itinerário de entrega
  payments/    gateway Stone + driver simulado
  cart/ accounts/ shipping/ subscriptions/ notifications/ assistant/ blog/
static/css/    design-system.css · layout.css · responsive.css · motion.css
static/js/     app.js (loja) · painel.js (painel) · assistente.js (Silvinha)
templates/     base.html, partials/, core/secoes/ (blocos da home)
docs/manual/   MANUAL.md (17 seções) + prints + PDF A4
```

Peças que concentram decisão:

- **`SiteConfig`** (`apps/core/models.py`): quase toda configuração da loja. É
  singleton, `SiteConfig.load()`.
- **`apps/dashboard/gestao.py`**: as telas de conteúdo (banners, cidades,
  cupons, linhas…) são **uma** view genérica guiada pelo dicionário `SECOES`.
  Para criar uma tela de cadastro nova, acrescente uma `Secao` ali — não
  escreva view nem template.
- **`ProdutoQuerySet.publicados()`**: filtra publicado **e** fora da lixeira. É
  por onde a loja inteira passa; mudanças de visibilidade moram aqui.

---

## 6. Decisões já tomadas (não reabra sem o usuário pedir)

| Assunto | Decisão |
|---|---|
| Aprovação de pedido | **Removida.** Faltou item, o lojista fala com o cliente no WhatsApp. |
| Estoque | Padrão **sem controle** (`sem_controle_estoque=True`): vende sempre. |
| Excluir produto | **Lixeira** (`excluido_em`). Apagar de vez é impossível: pedido e assinatura usam FK `PROTECT`. |
| Linhas (Premium…) | Cadastro (`LinhaProduto`), com cor livre, PNG e tamanho do selo. |
| Modal do painel | **Estático**: não fecha por clique no fundo nem por Esc. Só X/Cancelar. |
| Rascunho do cadastro | `localStorage`, por aparelho, 7 dias, some ao salvar. Fotos não entram. |
| WhatsApp Web | Aceito **com risco declarado**: fere os termos, o número pode cair. Usar chip dedicado. |
| Banner "apresentação" | Entra **sem** faixa de texto: a arte já traz o texto. |

---

## 7. Armadilhas que custam tempo

1. **`--noreload` cacheia template/view/templatetag** → reinicie o servidor.
2. **Navegador headless cacheia CSS/JS** mesmo com `Network.setCacheDisabled`.
   Se uma mudança de CSS "não aplicou", **mate o `msedge.exe`** e apague o
   diretório de cache do perfil antes de concluir que o código está errado.
   Isso já gerou mais de uma caçada a um bug inexistente.
3. **Heredoc do bash com apóstrofo quebra** (`unexpected EOF`). O caminho que
   funciona: escrever um script `.py` no scratchpad e executá-lo.
4. **`{# … #}` não pode ter várias linhas** — o texto vaza para o HTML. Use
   `{% comment %}`. Existe teste para isso.
5. **`position: fixed` dentro de elemento com `transform`** deixa de medir a
   tela (a animação `data-reveal` usa transform). Foi o que prendeu o visor da
   foto dentro da moldura no celular. Solução: mover o elemento para o `<body>`.
6. **`autoplay` de vídeo só vale no carregamento.** Slide que nasce escondido
   nunca começa — chame `play()` ao exibir.
7. **Grid com `1fr`** cresce até o conteúdo mais largo e estoura o celular. Use
   `minmax(0, 1fr)`.
8. **Repositório público**: chave privada **nunca** entra. Há `.gitignore` e um
   hook `.githooks/pre-commit` que barra `-----BEGIN ... PRIVATE KEY-----`.

---

## 8. Estado em 10/10/2026

Produção e `main` no mesmo commit. Suíte verde (~300 testes).

### Pendente comigo (código)

- **Prints e PDF do manual desatualizados** (são de 21/09): não mostram a logo
  nova, os selos coloridos, a busca corrigida, as telas de conta, os filtros
  por coluna, a lixeira nem o rascunho. Ferramenta de captura: ver seção 9.
- **SMTP não configurado.** `config/settings.py` já lê `EMAIL_HOST` e
  companhia do `.env`; sem isso fica no backend de console e **a loja não
  envia e-mail nenhum**. Falta o usuário escolher o provedor. Documentado na
  seção 12.1 do manual.
- **Um relato em aberto:** o usuário disse ter visto "texto de comentário do
  Django vazando". Varri mais de 30 telas (loja, checkout, conta, painel,
  fragmentos de modal), local e produção, e cruzei o texto de 167 comentários
  dos templates contra o HTML renderizado: **nada encontrado**. Está esperando
  ele dizer em qual tela foi. Se voltar ao assunto, peça o print.

### Pendente do lojista (dados, não código)

| O que | Estado |
|---|---|
| Stone | driver em **simulado** → não movimenta dinheiro. Manual em `/painel/manual/stone/`. |
| WhatsApp automático | desligado, falta ler o QR |
| Linha dos produtos | **39 dos 77 sem linha** → sem selo e fora das vitrines |
| Cidades de entrega | **1 cadastrada** (Valença) |
| Banners | 3; faltam cartazes 16:5 e ofertas em destaque |
| Gemini (Silvinha) | chave temporária |

> **Aviso para quem for mexer na Stone:** as URLs base que vêm por padrão no
> painel (`sandbox-api.stone.com.br`, `api.stone.com.br`) **não respondem** —
> verificado. A URL real vem da Stone na abertura da conta.

---

## 9. Ferramentas de verificação (scratchpad, fora do repo)

Existem utilitários de captura e inspeção via **CDP no Edge headless**:

- `shot.py lista.json saida/` — prints de tela; aceita `modo` (desktop/celular),
  `quem` (anon/cliente/lojista, por cookie de sessão), `eval` (JS antes do
  print), `altura`, `scroll`.
- `clique.py url` — roda `clique2.js` na página e devolve JSON. Serve para
  medir layout, conferir sobreposição, simular clique e testar fluxo.
- `sessoes.json` — cookies de sessão. **Expiram.** Para recriar, monte um
  `SessionStore` com o backend certo:
  `apps.accounts.backends.EmailOrUsernameBackend` (usar `ModelBackend` gera
  sessão que o Django recusa — já custou tempo).

Não existe teste de JS automatizado: o que é JS se verifica no navegador, com
esses scripts.

---

## 10. Onde continuar

Ordem sugerida, se o usuário não disser outra coisa:

1. Perguntar onde ele viu o comentário vazando (relato em aberto).
2. Regerar os prints e o PDF do manual.
3. SMTP, assim que ele escolher o provedor.
4. Acompanhar os itens do lojista — principalmente a Stone, que é o que separa
   a loja de vender de verdade.
