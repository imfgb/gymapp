#!/usr/bin/env bash
# Arranca GymApp en "modo wifi" para abrirlo desde tu teléfono (mismo wifi).
# Uso:  ./wifi.sh            (puerto 8001 por defecto)
#       ./wifi.sh 8002       (otro puerto, si 8001 está ocupado)
set -e
cd "$(dirname "$0")"                       # corre desde la carpeta del repo
PORT="${1:-8001}"
source .venv/bin/activate

# IP de la Mac en el wifi (en0 = Wi-Fi normal; en1 de respaldo)
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"

echo "=================================================================="
echo "   GymApp — modo wifi (Ctrl+C para detener)"
if [ -n "$IP" ]; then
  echo "   📱 En tu iPhone (mismo wifi):  http://$IP:$PORT"
else
  echo "   ⚠  No detecté IP de wifi — ¿estás conectado a una red?"
fi
echo "   💻 En esta Mac:               http://127.0.0.1:$PORT"
echo "=================================================================="

exec python manage.py runserver "0.0.0.0:$PORT"
