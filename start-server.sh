#!/usr/bin/env bash
# Запуск opencode-сервера с подхватом секретов из .env.
# ВАЖНО: сначала включи VPN. После обрыва VPN/сна — перезапусти этот скрипт.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Нет .env — скопируй .env.example в .env и заполни." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

echo "Стартую opencode serve на :4096 (VPN должен быть включён)…"
exec opencode serve --port 4096 --log-level DEBUG --print-logs
