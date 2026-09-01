# Dados de deploy — AgroCampo (modelo)

> Este é o **modelo versionado**, sem segredos. Os valores reais ficam em
> `deploy/DADOS-DE-DEPLOY.md`, que está no `.gitignore` porque este
> repositório é público.
>
> Ao clonar o projeto num ambiente novo, copie este arquivo para
> `deploy/DADOS-DE-DEPLOY.md` e preencha os campos entre `< >`.

Atualizado em 23/08/2026.

---

## 1. Endereços

| | |
|---|---|
| Loja | https://agrocampo.online |
| Painel do lojista | https://agrocampo.online/painel/ |
| Admin do Django (analista) | https://agrocampo.online/admin/ |
| Repositório | git@github.com:kauasantossacramento/agrocampo.git (público) |
| Branch de produção | `main` |

## 2. Servidor

| | |
|---|---|
| Host | `<IP do servidor>` (servidor dedicado nuvem.center) |
| Usuário | `root` |
| Chave SSH | `<caminho da chave SSH>` |
| Cópia para outras máquinas | `deploy/chaves/` — ver `deploy/chaves/README.md` |
| Diretório da aplicação | `/opt/agrocampo` |

```bash
ssh -i "<caminho da chave SSH>" root@<IP do servidor>
```

> O servidor hospeda o Nuvem Center e seus tenants. **Nada fora de
> `/opt/agrocampo` deve ser alterado.** Detalhes e provas de verificação em
> `deploy/RELATORIO-SERVIDOR.md`.

## 3. Acesso administrativo da loja

| | |
|---|---|
| E-mail | `admin@agrocampo.online` |
| Senha | `<senha do admin — ver deploy/DADOS-DE-DEPLOY.md>` |

Esse usuário é superusuário: vê o painel do lojista **e** o admin do Django.

> **Troque esta senha no primeiro acesso.** Ela foi gerada pelo instalador e
> passou por e-mail/chat. Em Perfil → alterar senha, ou:
> ```bash
> docker exec -it agrocampo-web python manage.py changepassword admin@agrocampo.online
> ```
> Depois de trocar, atualize `AGROCAMPO_ADMIN_SENHA` no `.env` do servidor —
> senão o próximo restart do container volta a senha antiga.

## 4. Banco de dados

Postgres 16, **sem porta publicada**: só é acessível de dentro da rede
`agrocampo_interna`.

| | |
|---|---|
| Banco | `agrocampo` |
| Usuário | `agrocampo` |
| Senha | `<senha do Postgres — ver deploy/DADOS-DE-DEPLOY.md>` |
| Host (interno) | `db:5432` |

```bash
# console psql
docker exec -it agrocampo-db psql -U agrocampo agrocampo
```

## 5. Variáveis de ambiente

Ficam em `/opt/agrocampo/.env` no servidor — **nunca no Git**.

| Variável | Valor em produção |
|---|---|
| `DJANGO_SECRET_KEY` | gerada na instalação; começa com `<gerada na instalação>` |
| `DJANGO_ALLOWED_HOSTS` | `agrocampo.online,www.agrocampo.online,agrocampo-nginx,localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://agrocampo.online,https://www.agrocampo.online` |
| `DJANGO_LOG_LEVEL` | `INFO` |
| `POSTGRES_DB` / `POSTGRES_USER` | `agrocampo` / `agrocampo` |
| `POSTGRES_PASSWORD` | ver seção 4 |
| `DEFAULT_FROM_EMAIL` | `AgroCampo <nao-responda@agrocampo.online>` |
| `DJANGO_EMAIL_BACKEND` | console (e-mail ainda **não** sai de verdade) |
| `AGROCAMPO_SEED` | `1` — só popula se o catálogo estiver vazio |
| `AGROCAMPO_ADMIN_EMAIL` / `_SENHA` | ver seção 3 |
| `STONE_*` | `sandbox`, **vazias** — ver seção 8 |

> O instalador preserva a `DJANGO_SECRET_KEY` entre atualizações. Trocá-la
> derruba todas as sessões e invalida os links de recuperação de senha.

## 6. Containers

| Container | Imagem | CPU / RAM |
|---|---|---|
| `agrocampo-web` | build local (`agrocampo/web:latest`) | 2,0 / 2 GB |
| `agrocampo-db` | `postgres:16-alpine` | 1,0 / 1 GB |
| `agrocampo-nginx` | `nginx:1.27-alpine` | 0,5 / 256 MB |
| `agrocampo-cron` | build local | 0,5 / 512 MB |

Volumes: `agrocampo_dados_db`, `agrocampo_media`, `agrocampo_estaticos`.

Redes: `agrocampo_interna` (própria) e `nuvem_net` (externa — só o nginx,
para receber do Traefik).

## 7. Deploy

Sequência usada em todas as entregas:

```bash
ssh -i "<caminho da chave SSH>" root@<IP do servidor>
cd /opt/agrocampo

# 1. backup antes de qualquer migração
docker exec agrocampo-db pg_dump -U agrocampo agrocampo \
  | gzip > /root/backup-agrocampo-$(date +%Y%m%d-%H%M).sql.gz

# 2. código
git pull --ff-only origin main

# 3. imagem
docker compose build web

# 4. migrações em container descartável
docker compose run --rm --no-deps web python manage.py migrate

# 5. troca só a aplicação
docker compose up -d --no-deps web
```

**`--no-deps` é obrigatório.** Sem ele o Compose recria o container do banco
e a loja responde 500 (`failed to resolve host 'db'`) durante a janela.

### Quando `deploy/nginx.conf` mudar

O arquivo entra como *bind mount de arquivo único*. O `git pull` grava um
inode novo e o container continua lendo o antigo — `nginx -s reload` não
resolve. É preciso recriar:

```bash
docker compose up -d --no-deps --force-recreate nginx
```

### Rollback

```bash
cd /opt/agrocampo
git checkout <commit-anterior>
docker compose build web && docker compose up -d --no-deps web

# só se precisar descartar dados novos:
gunzip -c /root/backup-agrocampo-AAAAMMDD-HHMM.sql.gz \
  | docker exec -i agrocampo-db psql -U agrocampo agrocampo
```

Backups ficam em `/root/backup-agrocampo-*.sql.gz`. **Não há rotação
automática** — vale apagar os antigos de tempos em tempos.

## 8. Pagamentos (Stone)

**Nenhuma transação real acontece hoje.** As credenciais da Stone estão
vazias e o sistema roda no driver simulado — a loja aceita pedidos, mas não
movimenta dinheiro.

Para ativar, cadastre as credenciais em
**Painel → Configurações → Pagamentos** (ficam no banco, não no `.env`, e
não exigem deploy). São necessárias:

`stone_client_id`, `stone_client_secret`, `stone_api_key`,
`stone_merchant_id`, `stone_affiliation_code`, `stone_webhook_secret`,
`stone_pix_chave`.

O driver só sai de "simulado" quando `api_key` **e** `merchant_id` estiverem
preenchidos.

## 9. Roteamento e TLS

O TLS termina no **Traefik do Nuvem Center**, que já existia no servidor. A
rota do AgroCampo é um arquivo só:

```
/opt/nuvem-center/docker/traefik/dynamic/agrocampo.yml
md5: 79ae25137eede851e1a4ce31fa2c3c23   (inalterado desde 21/08)
```

> Esse é o **único** arquivo meu naquele diretório. Não use o md5 do
> diretório inteiro como prova de que nada foi mexido: o Nuvem Center
> provisiona tenants sozinho e reescreve os outros arquivos.

Se algum script do Nuvem Center regenerar a pasta inteira, essa rota some e
`agrocampo.online` sai do ar. O arquivo de origem está versionado em
`deploy/traefik-agrocampo.yml`.

## 10. Limites de upload

| Camada | Limite |
|---|---|
| nginx (`client_max_body_size`) | 80 MB |
| Aplicação — vídeo de banner | 60 MB |
| Aplicação — imagens | 10 MB |
| Painel (aviso antes de enviar) | mesmos da aplicação |

O corte que o lojista enxerga é o da aplicação, que explica o motivo e diz o
tamanho do arquivo. O nginx é só a rede de segurança.

## 11. O que ainda falta configurar

Nada disso foi preenchido, de propósito — são dados do negócio, não meus:

- **Contato**: telefone, WhatsApp, endereço, e-mail e horário estão vazios.
  Sem WhatsApp cadastrado, o balão flutuante não aparece.
- **Entrega**: nenhuma cidade cadastrada. Até a primeira, o frete usa o valor
  global de `SiteConfig.frete_valor`.
- **Linhas**: os 4 produtos receberam Ouro/Prata/Bronze **como exemplo**,
  distribuídos por preço. Reclassifique no cadastro do produto.
- **E-mail**: o backend é console — nenhuma mensagem sai. Para enviar de
  verdade, configure SMTP no `.env`.
- **Firebase** (notificações push): campos vazios em Configurações →
  Notificações.
- **WhatsApp automático**: avaliação e o que falta em
  `docs/WHATSAPP-NOTIFICACOES.md`.

## 12. Higiene destas credenciais

- Este arquivo está fora do Git. **Não o commite.**
- A senha do admin e a do Postgres circularam por chat. Trate as duas como
  comprometidas e troque quando puder — a do admin pela tela, a do Postgres
  com `ALTER USER` seguido de atualizar o `.env` e recriar `web` e `db`.
- A chave SSH `nuvem-center-prod` dá acesso **root ao servidor inteiro**,
  incluindo o Nuvem Center e todos os tenants. Ela não pertence só a este
  projeto.
