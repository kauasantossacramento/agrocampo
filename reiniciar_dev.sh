#!/usr/bin/env bash
# Reinicia o servidor de desenvolvimento.
#
# Rodamos com --noreload porque o autoreloader do Django briga com a captura
# headless; o preco e que mudanca em template ou em .py so vale depois de
# reiniciar. Este script existe para nao esquecer disso.
set -e
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*runserver*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null || true
sleep 1
nohup ./.venv/Scripts/python.exe manage.py runserver 8765 --noreload > /dev/null 2>&1 &
for _ in $(seq 1 20); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/ || true)" = "200" ]; then
    echo "servidor no ar"; exit 0
  fi
  sleep 1
done
echo "servidor nao subiu"; exit 1
