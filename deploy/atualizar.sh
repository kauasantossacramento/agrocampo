#!/usr/bin/env bash
#
# Atualiza a aplicação já instalada: puxa o código, aplica migrações,
# recoleta estáticos e reinicia o serviço. Sem tocar em banco nem em .env.
#
#     sudo bash /opt/agrocampo/deploy/atualizar.sh
#
set -Eeuo pipefail

APP=agrocampo
DIR_APP="/opt/${APP}"
USUARIO_APP=$APP

VERDE=$'\e[32m'; FIM=$'\e[0m'
ok() { printf '%s  ✓%s %s\n' "$VERDE" "$FIM" "$1"; }

[[ $EUID -eq 0 ]] || { echo "Rode como root."; exit 1; }
cd "$DIR_APP"

sudo -u "$USUARIO_APP" git pull --ff-only
ok "código atualizado"

"$DIR_APP/.venv/bin/pip" install -r requirements.txt -q
ok "dependências"

sudo -u "$USUARIO_APP" "$DIR_APP/.venv/bin/python" manage.py migrate --noinput
sudo -u "$USUARIO_APP" "$DIR_APP/.venv/bin/python" manage.py collectstatic --noinput >/dev/null
ok "migrações e estáticos"

systemctl restart ${APP}.service
sleep 2
systemctl is-active --quiet ${APP}.service || { journalctl -u ${APP} -n 30 --no-pager; exit 1; }
ok "serviço reiniciado"
