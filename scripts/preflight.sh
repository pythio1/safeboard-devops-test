#!/usr/bin/env bash
# Проверка окружения ДО запуска: bash scripts/preflight.sh
bad=0
ok()   { echo "  OK    $*"; }
fail() { echo "  FAIL  $*"; bad=1; }
warn() { echo "  WARN  $*"; }

command -v docker >/dev/null && ok "docker: $(docker --version)" || fail "docker не найден"
docker info >/dev/null 2>&1 && ok "демон Docker отвечает" || fail "демон Docker недоступен (запущен ли Docker Desktop / dockerd? для WSL — включена ли интеграция?)"
docker compose version >/dev/null 2>&1 && ok "docker compose: $(docker compose version --short)" || fail "нет плагина docker compose"
command -v dagger >/dev/null && ok "dagger: $(dagger version 2>/dev/null | head -1)" || fail "dagger не найден (см. README, шаг 1)"
[ -S /var/run/docker.sock ] && ok "сокет /var/run/docker.sock существует" || fail "нет /var/run/docker.sock"
[ -s .env ] && ok ".env на месте" || fail ".env нет — выполните ./scripts/init-env.sh"
for p in 3000 3001 9090; do
  if (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null; then warn "порт $p занят (если это уже ваш стенд — нормально, иначе будет конфликт)"; else ok "порт $p свободен"; fi
done
[ "$bad" -eq 0 ] && echo "Preflight пройден" || echo "Preflight: есть проблемы"
exit "$bad"
