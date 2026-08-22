# Relatório de implantação — servidor dedicado nuvem.center

**Host:** `65.108.46.17` · Debian trixie · 12 vCPU · 62 GB RAM · 436 GB (md2)
**Domínio implantado:** `agrocampo.online` (+ `www`)
**Data:** 21/08/2026
**Executado por:** Claude (Opus 5), a pedido de Kauã Santos Sacramento

Este documento existe para que outro analista consiga auditar exatamente o
que foi feito, reverter se quiser, e confirmar que **nada do que já rodava
foi alterado**.

---

## 1. Resumo em uma linha

O AgroCampo subiu como um **stack Docker próprio e isolado** em `/opt/agrocampo`,
publicado pelo Traefik já existente através de **um único arquivo novo** no
diretório dinâmico. Nenhum arquivo, container, volume ou rede pré-existente
foi modificado.

---

## 2. O que foi inspecionado antes de agir

Levantamento somente-leitura, antes de qualquer escrita:

| Verificação | Resultado |
|---|---|
| Virtualização disponível | Docker (sem libvirt/qemu/lxc instalados) |
| `/dev/kvm` | presente, mas sem ferramental de VM |
| Quem detém 80/443 | `nuvem-traefik` (Traefik v3.5) |
| Providers do Traefik | **apenas `file`** — provider docker removido de propósito |
| Diretório dinâmico | `/opt/nuvem-center/docker/traefik/dynamic`, `watch: true` |
| Resolver de certificado | `letsencrypt` (HTTP challenge no entrypoint `web`) |
| Stack existente | 18 containers `nuvem-*` (Nextcloud multi-tenant, painel, site, OnlyOffice, netdata, uptime-kuma) |
| DNS `agrocampo.online` | já apontando para `65.108.46.17` |

---

## 3. Decisão de arquitetura — e por que não é uma VM

O pedido original era "uma máquina virtual, como uma VPS dentro do dedicado".
**Não foi entregue uma VM de verdade.** Motivo:

- o host não tem `libvirt`, `qemu` nem `virt-install`;
- instalar uma stack de virtualização completa num servidor que já serve
  três tenants Nextcloud em produção seria uma mudança grande, exigiria
  pacotes novos e possivelmente reboot — exatamente o tipo de risco que a
  instrução "não mexer no que existe" pede para evitar.

O que foi entregue no lugar: um **stack Docker isolado**, com

- rede interna própria (`agrocampo_interna`) — os containers do AgroCampo
  não enxergam os containers do Nuvem Center e vice-versa;
- volumes próprios (`agrocampo_dados_db`, `agrocampo_media`, `agrocampo_estaticos`);
- **teto de CPU e memória por container** (a parte de "recursos básicos");
- banco próprio (PostgreSQL 16), sem porta publicada no host.

Isso dá isolamento de rede, de dados e de recursos. **Não dá isolamento de
kernel** — é a diferença real para uma VM. Se o requisito for isolamento de
kernel, é preciso instalar KVM/libvirt e refazer, e isso é uma decisão sua.

---

## 4. O que foi CRIADO (tudo novo, nada sobrescrito)

### 4.1 Diretório da aplicação

```
/opt/agrocampo/                 clone de github.com/kauasantossacramento/agrocampo
├── .env                        segredos, modo 600, dono root
├── CREDENCIAIS.txt             resumo de acesso, modo 600
├── docker-compose.yml
└── deploy/nginx.conf
```

Nada foi escrito em `/opt/nuvem-center/**` exceto o item 4.3.

### 4.2 Containers, volumes e rede

| Container | Imagem | Limite | Função |
|---|---|---|---|
| `agrocampo-nginx` | `nginx:1.27-alpine` | 0.5 CPU / 256 MB | borda: `/static/`, `/media/`, proxy |
| `agrocampo-web` | `agrocampo/web:latest` (build local) | 2 CPU / 2 GB | Django + Gunicorn (3 workers) |
| `agrocampo-db` | `postgres:16-alpine` | 1 CPU / 1 GB | banco |
| `agrocampo-cron` | `agrocampo/web:latest` | 0.5 CPU / 512 MB | assinaturas, 06:00 |

Rede criada: `agrocampo_interna` (bridge).
Rede **usada como externa, sem alteração**: `nuvem_net` — só o `agrocampo-nginx`
se conecta a ela, e apenas para o Traefik conseguir alcançá-lo.

Volumes criados: `agrocampo_dados_db`, `agrocampo_media`, `agrocampo_estaticos`.

**Nenhuma porta do host foi publicada.** O stack é alcançável só pela rede
interna do Docker e pelo Traefik.

### 4.3 O único arquivo escrito fora de `/opt/agrocampo`

```
/opt/nuvem-center/docker/traefik/dynamic/agrocampo.yml   (novo, root:root 644)
```

Conteúdo: um router `agrocampo` e um service apontando para
`http://agrocampo-nginx:80`, com `certResolver: letsencrypt` e o middleware
`compressao@file`.

Por que aqui: o Traefik deste host tem **apenas o provider `file`** — labels
no container não são lidas, então não havia outro caminho.

Por que é seguro:

- é um **arquivo novo**; nenhum `.yml` existente foi tocado;
- `providers.file.watch: true` carregou a rota **sem reiniciar o Traefik**;
- md5 de todos os arquivos pré-existentes foi conferido antes e depois — **idênticos**:

```
cde8b27ae5bb7f21f2ff6f5aff893add  middlewares.yml
a6d89e96d4ea0ebefa105e1ed87b7b32  servicos.yml
2abadfdc8cba05c182b8bd79f1dd5a3b  tenant-conmac.yml
423552eda370d747090cb3e9dd9ab088  tenant-empresa-de-teste-2.yml
e11975dca8389ba23a411281f16bb8c0  tenant-empresa-de-teste-3.yml
```

O nome `agrocampo.yml` foge do padrão `tenant-*.yml` de propósito: deixa
óbvio que não é um tenant do Nuvem Center e que os scripts de tenant
(`provision-tenant.sh`, `suspend-tenant.sh`) não devem tocá-lo.

### 4.4 Certificado TLS

Emitido pelo resolver `letsencrypt` que já existia, gravado no volume
`docker_traefik_acme` que o Traefik já usava. Cobre `agrocampo.online` e
`www.agrocampo.online`, válido até 19/11/2026, renovação automática pelo
mesmo mecanismo dos demais domínios.

---

## 5. O que NÃO foi tocado

- `/opt/nuvem-center/docker/docker-compose*.yml`
- `traefik.yml` (configuração estática)
- `middlewares.yml`, `servicos.yml`, `tenant-*.yml`
- qualquer container, volume ou rede `nuvem-*` / `nuvem_*`
- `sshd`, `fail2ban`, `ufw`, `mdadm`
- pacotes do sistema — **nenhum `apt install` foi executado**
- crontab do host (o cron do AgroCampo vive dentro de um container)

---

## 6. Verificação pós-implantação

Serviços pré-existentes, checados **depois** da publicação:

| Alvo | HTTP | Observação |
|---|---|---|
| `https://nuvem.center/` | 200 | |
| `https://www.nuvem.center/` | 200 | |
| `https://conmac.nuvem.center/` | 302 | redirect de login do Nextcloud (normal) |
| `https://agrocampo.online/` | 200 | |

Uptime dos containers pré-existentes conferido após a mudança: **2 a 4 dias**,
ou seja, os valores originais. O próprio `nuvem-traefik` permaneceu com
"Up 3 days" — confirmando que não houve restart.

Consumo do stack novo em repouso:

```
agrocampo-nginx   0.17%   10 MiB / 256 MiB
agrocampo-web     4.48%  189 MiB / 2 GiB
agrocampo-db      3.58%   31 MiB / 1 GiB
agrocampo-cron    0.00%  0.7 MiB / 512 MiB
```

RAM do host após a implantação: 3.8 GB de 62 GB.

---

## 7. Operação

```bash
# status / logs
docker compose -f /opt/agrocampo/docker-compose.yml ps
docker compose -f /opt/agrocampo/docker-compose.yml logs -f web

# atualizar a aplicação
cd /opt/agrocampo && git pull && docker compose up -d --build

# reiniciar só a aplicação (não toca no banco)
docker compose -f /opt/agrocampo/docker-compose.yml restart web
```

Credenciais em `/opt/agrocampo/CREDENCIAIS.txt` (modo 600).

---

## 8. Como reverter por completo

```bash
# 1. tira a rota (o Traefik reage sozinho, sem restart)
rm /opt/nuvem-center/docker/traefik/dynamic/agrocampo.yml

# 2. derruba o stack e os volumes
cd /opt/agrocampo && docker compose down -v

# 3. remove a aplicação e a imagem
rm -rf /opt/agrocampo
docker rmi agrocampo/web:latest
```

Depois disso o host volta exatamente ao estado anterior. Nenhum pacote,
serviço do sistema ou arquivo do Nuvem Center precisa ser desfeito, porque
nenhum foi alterado.

---

## 9. Pontos de atenção para o analista

1. **Não é VM.** Isolamento de rede/dados/recursos, sim; de kernel, não.
   Ver seção 3.
2. **Um arquivo fora do diretório da aplicação.** O `agrocampo.yml` no
   dynamic do Traefik. Se algum script de deploy do Nuvem Center regenerar
   aquele diretório inteiro, essa rota some e `agrocampo.online` sai do ar —
   vale checar se `render-config.sh` limpa a pasta.
3. **Sem porta publicada.** O Postgres do AgroCampo não é acessível do host
   nem da rede; só de dentro de `agrocampo_interna`.
4. **`docker compose up -d` recria o container do banco quando o compose
   muda.** Durante essa janela a aplicação responde 500 (`failed to resolve
   host 'db'`). Já mitigado com `CONN_HEALTH_CHECKS`, mas para atualizações
   prefira `docker compose up -d --no-deps web`.
5. **Modo simulado de pagamento.** Enquanto as credenciais da Stone não
   forem cadastradas em `/painel/configuracoes/`, nenhuma transação real
   acontece — a loja aceita pedidos, mas não movimenta dinheiro.

---

## 10. Atualização de 22/08/2026 — entrega, tamanhos e linhas

Segunda intervenção no servidor. Mesmo princípio da primeira: **nada fora de
`/opt/agrocampo` foi tocado**.

### O que foi executado, na ordem

```bash
# 1. backup do banco antes de qualquer migração
docker exec agrocampo-db pg_dump -U agrocampo agrocampo \
  | gzip > /root/backup-agrocampo-20260822-1142.sql.gz     # 26 KB

# 2. código novo
cd /opt/agrocampo && git pull --ff-only origin main        # 5226d32 -> a03d719

# 3. imagem da aplicação (só o serviço web)
docker compose build web

# 4. migrações, em container descartável e sem subir dependências
docker compose run --rm --no-deps web python manage.py migrate

# 5. troca só do container da aplicação
docker compose up -d --no-deps web
```

### Migrações aplicadas

| App | Migração |
|---|---|
| shipping | `0001_initial` (app novo: Cidade, Localidade, RegraEntrega) |
| accounts | `0002_endereco_cidade_atendida_endereco_localidade_and_more` |
| catalog | `0007_produto_linha_alter_produto_unidade_variacaoproduto` |
| cart | `0003_alter_itemcarrinho_unique_together_and_more` |
| core | `0006_siteconfig_aviso_entrega_and_more` |
| core | `0007_banner_produtos_alter_banner_posicao` |
| core | `0008_siteconfig_logo_altura` |
| orders | `0004_itempedido_variacao_itempedido_variacao_rotulo_and_more` |

Todas aditivas: campos e tabelas novas. Nenhuma coluna removida ou renomeada,
nenhum dado existente reescrito pelas migrações.

### Dados alterados à mão (só dois comandos)

1. **`SiteConfig.horario_atendimento` esvaziado.** O valor `"Seg a sex, 8h às
   18h · Sáb, 8h às 12h"` era invenção minha da primeira rodada, remanescente
   da limpeza anterior. A loja informa o horário real pelo painel.
2. **Ordem das espécies.** Cão e Gato estavam nas posições 20 e 21 e o corte
   da vitrine era 14, então nunca apareciam na home. Reordenados conforme a
   lista do `seed.py`. O comando só fez `UPDATE ordem, destaque_home` em
   registros já existentes — não criou, não apagou, não renomeou nada.

### Verificação depois do deploy

| Item | Antes | Depois |
|---|---|---|
| `md5sum` dos 7 arquivos em `traefik/dynamic/` | — | **idênticos** |
| Containers `nuvem-*` | 15 no ar | 15 no ar, **sem reinício** |
| `https://nuvem.center/` | — | 200 |
| `https://conmac.nuvem.center/` | — | 302 (comportamento normal) |
| `agrocampo-db`, `-nginx`, `-cron` | up 35h | **up 35h** (não recriados) |
| `agrocampo-web` | up 23h | recriado, `healthy` |

Rotas conferidas em produção: `/`, `/catalogo/`, `/catalogo/?linha=ouro`,
`/carrinho/`, `/conta/cadastrar/`, `/entrega/onde-entregamos/` → todas 200;
`/painel/` → 302 para o login, como esperado.

### Estado dos dados após a atualização

Nada foi pré-preenchido. O lojista configura tudo pelo painel:

- Cidades atendidas: **0** — até cadastrar a primeira, o frete continua sendo
  o valor global de `SiteConfig.frete_valor`.
- Localidades e avisos de entrega: **0**.
- `entrega_a_partir_de`: **vazio**.
- Produtos com linha (Ouro/Prata/Bronze): **0** — as três vitrines da home só
  aparecem quando houver produto em cada linha.
- Variações (tamanhos): **0**.
- Telefone, WhatsApp, endereço, e-mail e horário: **todos vazios**.

> O `seed.py` cria a cidade de Valença/BA **desativada e com frete 0,00**, de
> propósito: uma cidade ativa com frete zero anunciaria entrega grátis, um
> preço que ninguém combinou. Em produção o seed não roda de novo (o
> entrypoint detecta catálogo populado), então nem essa cidade existe lá.

### Rollback desta atualização

```bash
cd /opt/agrocampo
git checkout 5226d32
docker compose build web && docker compose up -d --no-deps web
gunzip -c /root/backup-agrocampo-20260822-1142.sql.gz \
  | docker exec -i agrocampo-db psql -U agrocampo agrocampo
```

As migrações são aditivas, então voltar só o código já funciona; restaurar o
dump só é necessário se houver dados novos a descartar.
