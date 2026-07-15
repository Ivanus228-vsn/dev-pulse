#!/usr/bin/env bash
# Запуск Mattermost-бота с подхватом .env.
# Перед этим должен быть запущен start-server.sh (opencode на :4096).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

exec python3 mm_bot.py
