#!/usr/bin/env bash
#
# AgroCampo — instalação completa em VPS Ubuntu/Debian.
#
# Rode DEPOIS do git clone, de dentro da raiz do projeto:
#     sudo bash deploy/install.sh
#
# O script é idempotente: pode rodar de novo para atualizar a aplicação.
# Ele pergunta o domínio e o e-mail e configura tudo em cima disso —
# Postgres, venv, migrações, Gunicorn, Nginx, Let's Encrypt e o cron das
# assinaturas.
#
set -Eeuo pipefail

# ----------------------------------------------------------------- estética
VERMELHO=$'\e[31m'; VERDE=$'\e[32m'; AMARELO=$'\e[33m'; AZUL=$'\e[36m'
NEGRITO=$'\e[1m'; FIM=$'\e[0m'

titulo()  { printf '\n%s══ %s ══%s\n' "$AZUL$NEGRITO" "$1" "$FIM"; }
ok()      { printf '%s  ✓%s %s\n' "$VERDE" "$FIM" "$1"; }
aviso()   { printf '%s  !%s %s\n' "$AMARELO" "$FIM" "$1"; }
erro()    { printf '%s  ✗ %s%s\n' "$VERMELHO" "$1" "$FIM" >&2; }
morrer()  { erro "$1"; exit 1; }

trap 'erro "Falha na linha $LINENO. Nada foi revertido — corrija e rode de novo."' ERR

[[ $EUID -eq 0 ]] || morrer "Rode como root:  sudo bash deploy/install.sh"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"
[[ -f manage.py ]] || morrer "manage.py não encontrado. Rode de dentro da raiz do projeto."

# ------------------------------------------------------------------ entrada
titulo "Configuração"

perguntar() {                       # perguntar VAR "rótulo" "padrão"
  local __var=$1 rotulo=$2 padrao=${3:-} resposta
  if [[ -n "$padrao" ]]; then
    read -rp "  ${rotulo} [${padrao}]: " resposta
    resposta=${resposta:-$padrao}
  else
    while [[ -z "${resposta:-}" ]]; do read -rp "  ${rotulo}: " resposta; done
  fi
  printf -v "$__var" '%s' "$resposta"
}

perguntar_senha() {                 # perguntar_senha VAR "rótulo"
  local __var=$1 rotulo=$2 a b
  while :; do
    read -rsp "  ${rotulo}: " a; echo
    read -rsp "  confirme: " b; echo
    [[ "$a" == "$b" && -n "$a" ]] && break
    aviso "Senhas diferentes ou vazias. Tente de novo."
  done
  printf -v "$__var" '%s' "$a"
}

perguntar DOMINIO      "Domínio (ex.: agrocampo.online)"
perguntar EMAIL_CERT   "E-mail para o Let's Encrypt" "admin@${DOMINIO}"
perguntar USAR_WWW     "Incluir www.${DOMINIO} no certificado? (s/n)" "s"
perguntar ADMIN_EMAIL  "E-mail do administrador da loja" "admin@${DOMINIO}"
perguntar_senha ADMIN_SENHA "Senha do administrador"
perguntar SEMEAR       "Popular com catálogo de demonstração? (s/n)" "n"

DOMINIO=${DOMINIO#http://}; DOMINIO=${DOMINIO#https://}; DOMINIO=${DOMINIO%%/*}
[[ "$DOMINIO" =~ ^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] || morrer "Domínio inválido: $DOMINIO"

APP=agrocampo
USUARIO_APP=$APP
DIR_APP="/opt/${APP}"
DB_NOME=$APP
DB_USER=$APP
DB_SENHA="$(openssl rand -base64 30 | tr -d '/+=' | head -c 32)"
SECRET_KEY="$(openssl rand -base64 60 | tr -d '\n/+=' | head -c 64)"

HOSTS="${DOMINIO},127.0.0.1,localhost"
ORIGENS="https://${DOMINIO}"
ARGS_CERTBOT=(-d "$DOMINIO")
if [[ "${USAR_WWW,,}" == s* ]]; then
  HOSTS="${HOSTS},www.${DOMINIO}"
  ORIGENS="${ORIGENS},https://www.${DOMINIO}"
  ARGS_CERTBOT+=(-d "www.${DOMINIO}")
  NOMES_SERVIDOR="${DOMINIO} www.${DOMINIO}"
else
  NOMES_SERVIDOR="${DOMINIO}"
fi

echo
echo "  Domínio ......... ${DOMINIO}"
echo "  Aplicação em .... ${DIR_APP}"
echo "  Banco ........... postgres://${DB_USER}@localhost/${DB_NOME}"
echo "  Admin ........... ${ADMIN_EMAIL}"
read -rp "  Confirma? (s/N): " CONFIRMA
[[ "${CONFIRMA,,}" == s* ]] || morrer "Cancelado pelo usuário."

# ------------------------------------------------------------------ pacotes
titulo "Pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-dev build-essential \
  postgresql postgresql-contrib libpq-dev \
  nginx certbot python3-certbot-nginx \
  git curl ufw >/dev/null
ok "python3, postgresql, nginx, certbot"

# ------------------------------------------------------------------ usuário
titulo "Usuário e diretórios"
id -u "$USUARIO_APP" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$USUARIO_APP"
ok "usuário de sistema '${USUARIO_APP}'"

if [[ "$RAIZ" != "$DIR_APP" ]]; then
  mkdir -p "$DIR_APP"
  # -a preserva permissões; --delete manteria media/, então copiamos por cima
  cp -a "$RAIZ/." "$DIR_APP/"
  ok "código copiado para ${DIR_APP}"
fi
cd "$DIR_APP"
mkdir -p "$DIR_APP/media" "$DIR_APP/staticfiles" /var/log/${APP}
chown -R "$USUARIO_APP:$USUARIO_APP" "$DIR_APP" /var/log/${APP}

# ------------------------------------------------------------------- banco
titulo "PostgreSQL"
systemctl enable --now postgresql >/dev/null 2>&1 || true

existe_papel=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" || true)
if [[ "$existe_papel" == "1" ]]; then
  sudo -u postgres psql -qc "ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_SENHA}';" >/dev/null
  ok "papel '${DB_USER}' já existia — senha rotacionada"
else
  sudo -u postgres psql -qc "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_SENHA}';" >/dev/null
  ok "papel '${DB_USER}' criado"
fi

existe_db=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NOME}'" || true)
if [[ "$existe_db" != "1" ]]; then
  sudo -u postgres createdb -O "$DB_USER" -E UTF8 "$DB_NOME"
  ok "banco '${DB_NOME}' criado"
else
  ok "banco '${DB_NOME}' já existia — preservado"
fi
# o Django cria tabelas nas migrações; precisa poder criar no schema public
sudo -u postgres psql -q -d "$DB_NOME" -c "GRANT ALL ON SCHEMA public TO ${DB_USER};" >/dev/null

# --------------------------------------------------------------------- .env
titulo "Variáveis de ambiente"
if [[ -f "$DIR_APP/.env" ]]; then
  cp "$DIR_APP/.env" "$DIR_APP/.env.bak.$(date +%s)"
  # preserva a SECRET_KEY: trocá-la invalida sessões e tokens já emitidos
  ANTIGA=$(grep -oP '^DJANGO_SECRET_KEY=\K.*' "$DIR_APP/.env" || true)
  [[ -n "$ANTIGA" ]] && SECRET_KEY="$ANTIGA" && ok "SECRET_KEY existente preservada"
fi

cat > "$DIR_APP/.env" <<ENV
# Gerado por deploy/install.sh em $(date -Is)
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=${HOSTS}
DJANGO_CSRF_TRUSTED_ORIGINS=${ORIGENS}
DJANGO_LOG_LEVEL=INFO

DATABASE_URL=postgres://${DB_USER}:${DB_SENHA}@localhost:5432/${DB_NOME}

# E-mail: troque para SMTP real quando tiver as credenciais
DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=AgroCampo <nao-responda@${DOMINIO}>

# Stone — deixe vazio para operar em modo simulado.
# Em produção, cadastre pelo painel: /painel/configuracoes/
STONE_ENVIRONMENT=sandbox
STONE_CLIENT_ID=
STONE_CLIENT_SECRET=
STONE_API_KEY=
STONE_MERCHANT_ID=
STONE_AFFILIATION_CODE=
STONE_WEBHOOK_SECRET=
STONE_PIX_KEY=
ENV
chown "$USUARIO_APP:$USUARIO_APP" "$DIR_APP/.env"
chmod 600 "$DIR_APP/.env"
ok ".env gravado (600, só o dono lê)"

# ---------------------------------------------------------------- ambiente
titulo "Ambiente Python"
[[ -d "$DIR_APP/.venv" ]] || python3 -m venv "$DIR_APP/.venv"
"$DIR_APP/.venv/bin/pip" install --upgrade pip -q
"$DIR_APP/.venv/bin/pip" install -r "$DIR_APP/requirements.txt" -q
ok "venv + requirements"

# --------------------------------------------------------------- aplicação
titulo "Migrações e estáticos"
gerenciar() { sudo -u "$USUARIO_APP" "$DIR_APP/.venv/bin/python" "$DIR_APP/manage.py" "$@"; }

chown -R "$USUARIO_APP:$USUARIO_APP" "$DIR_APP"
gerenciar migrate --noinput
ok "migrações aplicadas"

gerenciar collectstatic --noinput >/dev/null
ok "estáticos coletados"

if [[ "${SEMEAR,,}" == s* ]]; then
  gerenciar seed >/dev/null && ok "catálogo de demonstração criado"
  # as fotos das espécies não vão no git (são geradas); baixa aqui.
  # Se a rede falhar, o site sobe do mesmo jeito, só sem as fotos.
  if gerenciar baixar_imagens >/dev/null 2>&1; then
    ok "fotos das espécies baixadas do Wikimedia Commons"
  else
    aviso "Não consegui baixar as fotos das espécies (rede?)."
    aviso "Rode depois:  sudo -u ${USUARIO_APP} ${DIR_APP}/.venv/bin/python ${DIR_APP}/manage.py baixar_imagens"
  fi
fi

# superusuário sem passar a senha por linha de comando (não vaza no ps/history)
ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_SENHA="$ADMIN_SENHA" gerenciar shell <<'PYCODE'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ["ADMIN_EMAIL"]
senha = os.environ["ADMIN_SENHA"]

usuario, criado = User.objects.get_or_create(
    email=email,
    defaults={"username": email, "first_name": "Administrador",
              "papel": "admin", "is_staff": True, "is_superuser": True},
)
usuario.is_staff = usuario.is_superuser = True
usuario.papel = "admin"
usuario.set_password(senha)
usuario.save()
print("criado" if criado else "atualizado")
PYCODE
ok "administrador ${ADMIN_EMAIL} pronto"

# ---------------------------------------------------------------- gunicorn
titulo "Gunicorn (systemd)"
NUCLEOS=$(nproc)
TRABALHADORES=$(( NUCLEOS * 2 + 1 ))
(( TRABALHADORES > 9 )) && TRABALHADORES=9

cat > /etc/systemd/system/${APP}.socket <<UNIT
[Unit]
Description=Socket do Gunicorn - AgroCampo

[Socket]
ListenStream=/run/${APP}.sock
SocketUser=www-data
SocketMode=660

[Install]
WantedBy=sockets.target
UNIT

cat > /etc/systemd/system/${APP}.service <<UNIT
[Unit]
Description=AgroCampo (Gunicorn)
Requires=${APP}.socket
After=network.target postgresql.service

[Service]
Type=notify
User=${USUARIO_APP}
Group=${USUARIO_APP}
RuntimeDirectory=${APP}
WorkingDirectory=${DIR_APP}
Environment=PYTHONUNBUFFERED=1
ExecStart=${DIR_APP}/.venv/bin/gunicorn \\
    --workers ${TRABALHADORES} \\
    --timeout 60 \\
    --graceful-timeout 30 \\
    --access-logfile - \\
    --error-logfile - \\
    --bind unix:/run/${APP}.sock \\
    config.wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3

# isolamento: o serviço só enxerga o que precisa
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${DIR_APP}/media ${DIR_APP}/staticfiles /var/log/${APP}

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now ${APP}.socket >/dev/null
systemctl restart ${APP}.service
sleep 2
systemctl is-active --quiet ${APP}.service \
  || morrer "Gunicorn não subiu. Veja: journalctl -u ${APP} -n 50 --no-pager"
ok "gunicorn ativo (${TRABALHADORES} workers)"

# ------------------------------------------------------------------- nginx
titulo "Nginx"
cat > /etc/nginx/sites-available/${APP} <<NGINX
upstream ${APP}_app {
    server unix:/run/${APP}.sock fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${NOMES_SERVIDOR};

    client_max_body_size 25M;

    # o certbot precisa deste caminho para validar o domínio
    location /.well-known/acme-challenge/ { root /var/www/html; }

    location /static/ {
        alias ${DIR_APP}/staticfiles/;
        expires 30d;
        access_log off;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias ${DIR_APP}/media/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://${APP}_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               image/svg+xml application/xml;
    gzip_min_length 512;
}
NGINX

ln -sfn /etc/nginx/sites-available/${APP} /etc/nginx/sites-enabled/${APP}
mkdir -p /var/www/html
nginx -t >/dev/null 2>&1 || morrer "Configuração do Nginx inválida. Rode: nginx -t"
systemctl reload nginx
ok "nginx servindo ${NOMES_SERVIDOR}"

# ------------------------------------------------------------------- HTTPS
titulo "Certificado Let's Encrypt"
IP_SERVIDOR=$(curl -fsS --max-time 8 https://api.ipify.org || echo "")
IP_DOMINIO=$(getent hosts "$DOMINIO" | awk '{print $1; exit}' || echo "")

if [[ -n "$IP_SERVIDOR" && -n "$IP_DOMINIO" && "$IP_SERVIDOR" != "$IP_DOMINIO" ]]; then
  aviso "${DOMINIO} aponta para ${IP_DOMINIO}, mas este servidor é ${IP_SERVIDOR}."
  aviso "O certificado vai falhar até o DNS propagar. Pulando o HTTPS."
  aviso "Depois rode:  certbot --nginx ${ARGS_CERTBOT[*]}"
  HTTPS_OK=nao
else
  if certbot --nginx "${ARGS_CERTBOT[@]}" \
       --non-interactive --agree-tos --email "$EMAIL_CERT" \
       --redirect --keep-until-expiring; then
    ok "HTTPS ativo e renovação automática configurada"
    HTTPS_OK=sim
  else
    aviso "O certbot falhou. O site segue no ar em HTTP."
    aviso "Tente depois:  certbot --nginx ${ARGS_CERTBOT[*]}"
    HTTPS_OK=nao
  fi
fi

# sem HTTPS, o redirect forçado do Django deixaria o site inacessível
if [[ "$HTTPS_OK" == "nao" ]]; then
  sed -i 's/^DJANGO_SECURE_SSL_REDIRECT=.*//' "$DIR_APP/.env"
  echo "DJANGO_SECURE_SSL_REDIRECT=False" >> "$DIR_APP/.env"
  systemctl restart ${APP}.service
  aviso "SSL redirect desligado até o certificado existir."
fi

# ----------------------------------------------------------- tarefa diária
titulo "Assinaturas recorrentes"
cat > /etc/cron.d/${APP}-assinaturas <<CRON
# Processa os ciclos de assinatura vencidos, todo dia às 6h
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 6 * * * ${USUARIO_APP} ${DIR_APP}/.venv/bin/python ${DIR_APP}/manage.py processar_assinaturas >> /var/log/${APP}/assinaturas.log 2>&1
CRON
chmod 644 /etc/cron.d/${APP}-assinaturas
ok "cron diário às 6h"

# ---------------------------------------------------------------- firewall
titulo "Firewall"
if ufw status | grep -q "Status: active"; then
  ufw allow 'Nginx Full' >/dev/null && ok "portas 80/443 liberadas"
else
  aviso "ufw inativo — não mexi nas regras para não cortar seu acesso."
  aviso "Se quiser ativar:  ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable"
fi

# ------------------------------------------------------------------ resumo
CREDENCIAIS="${DIR_APP}/CREDENCIAIS.txt"
cat > "$CREDENCIAIS" <<RESUMO
AgroCampo — instalado em $(date -Is)

Site .............. https://${DOMINIO}
Painel do lojista . https://${DOMINIO}/painel/
Admin Django ...... https://${DOMINIO}/admin/

Administrador
  e-mail .......... ${ADMIN_EMAIL}
  senha ........... (a que você digitou na instalação)

Banco de dados
  host ............ localhost:5432
  nome ............ ${DB_NOME}
  usuário ......... ${DB_USER}
  senha ........... ${DB_SENHA}

Serviço ........... systemctl {status|restart} ${APP}
Logs .............. journalctl -u ${APP} -f
Aplicação ......... ${DIR_APP}
Ambiente .......... ${DIR_APP}/.env

Próximo passo: cadastre as credenciais da Stone em
https://${DOMINIO}/painel/configuracoes/
RESUMO
chmod 600 "$CREDENCIAIS"

titulo "Pronto"
cat "$CREDENCIAIS"
echo
ok "Uma cópia deste resumo ficou em ${CREDENCIAIS} (só root lê)."
[[ "$HTTPS_OK" == "sim" ]] && ok "Acesse: https://${DOMINIO}" || aviso "Acesse: http://${DOMINIO}"
