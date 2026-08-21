#!/usr/bin/env bash
#
# Entrypoint do container: espera o banco, aplica migrações, coleta
# estáticos e entrega o processo ao comando recebido (gunicorn).
#
set -Eeuo pipefail

echo "[entrypoint] aguardando o banco..."
for tentativa in $(seq 1 60); do
  if python - <<'PY' 2>/dev/null
import os, sys
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection
connection.ensure_connection()
PY
  then
    echo "[entrypoint] banco respondeu na tentativa ${tentativa}"
    break
  fi
  if [[ $tentativa -eq 60 ]]; then
    echo "[entrypoint] banco nao respondeu em 60 tentativas" >&2
    exit 1
  fi
  sleep 2
done

echo "[entrypoint] migracoes..."
python manage.py migrate --noinput

echo "[entrypoint] estaticos..."
python manage.py collectstatic --noinput --clear >/dev/null

# Semeia apenas na primeira subida (banco ainda sem produtos nem config).
if [[ "${AGROCAMPO_SEED:-0}" == "1" ]]; then
  python - <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.catalog.models import Produto
from django.core.management import call_command

if not Produto.objects.exists():
    print("[entrypoint] catalogo vazio: populando")
    call_command("seed", verbosity=0)
    try:
        call_command("baixar_imagens", verbosity=0)
    except Exception as exc:                     # rede pode falhar; nao e fatal
        print(f"[entrypoint] imagens das especies nao baixadas: {exc}")
else:
    print("[entrypoint] catalogo ja populado: nada a fazer")
PY
fi

# Cria/atualiza o administrador a partir do ambiente, sem expor a senha em ps.
if [[ -n "${AGROCAMPO_ADMIN_EMAIL:-}" && -n "${AGROCAMPO_ADMIN_SENHA:-}" ]]; then
  python - <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ["AGROCAMPO_ADMIN_EMAIL"]
usuario, criado = User.objects.get_or_create(
    email=email,
    defaults={"username": email, "first_name": "Administrador",
              "papel": "admin", "is_staff": True, "is_superuser": True},
)
usuario.is_staff = usuario.is_superuser = True
usuario.papel = "admin"
usuario.set_password(os.environ["AGROCAMPO_ADMIN_SENHA"])
usuario.save()
print(f"[entrypoint] administrador {email} {'criado' if criado else 'atualizado'}")
PY
fi

echo "[entrypoint] iniciando: $*"
exec "$@"
