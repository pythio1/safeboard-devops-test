#!/bin/sh
# Chaos-тест. Использование: chaos.sh <mariadb|kuma> <kill|stop> [секунд_простоя_для_stop]
#
#  kill — `docker kill` (SIGKILL, как аварийное падение). Restart-policy ДОЛЖНА поднять контейнер сама.
#  stop — `docker stop`. Docker НЕ перезапускает вручную остановленный контейнер (так задумано),
#         поэтому скрипт держит простой N секунд, фиксирует «красный» статус, затем делает `docker start`.
#
# Проверяем: (а) статус на дашборде (через Grafana) стал 0 — «ВСЁ ПЛОХО»; (б) сервис вернулся и статус снова 1.
. "$(dirname "$0")/lib.sh"
TARGET="${1:-mariadb}"; MODE="${2:-kill}"; DOWN="${3:-25}"
case "$TARGET" in mariadb) C=safeboard-mariadb ;; kuma) C=safeboard-kuma ;; *) echo "target: mariadb|kuma"; exit 2 ;; esac
case "$MODE" in kill|stop) ;; *) echo "mode: kill|stop"; exit 2 ;; esac
QUERY="safeboard:overall_up"
# Есть ли у Grafana рабочий data source? Если нет (configure-grafana не запускали) — проверяем через Prometheus.
if [ -n "$(gval "$QUERY")" ]; then VIA=graf; else VIA=prom; echo "ВНИМАНИЕ: data source Grafana недоступен, проверяю через Prometheus"; fi
echo "Источник проверки: $VIA"

echo "[1/5] Базовая линия: платформа должна быть здорова"
wait_for "$VIA" "$QUERY" 1 120 || { echo "FAIL: до теста платформа уже нездорова"; exit 1; }
R0=$(restarts_of "$C"); START=$(date +%s)

echo "[2/5] Ломаем $C (docker $MODE)"
if [ "$MODE" = kill ]; then docker kill "$C" >/dev/null; else docker stop "$C" >/dev/null; fi

if [ "$MODE" = stop ]; then
  echo "[3/5] Ждём красный статус ($VIA:$QUERY == 0)"
  wait_for "$VIA" "$QUERY" 0 90 || { echo "FAIL (а): статус не стал 0"; docker start "$C" >/dev/null; exit 1; }
  echo "      OK (а): дашборд показывает «ВСЁ ПЛОХО». Держим простой ${DOWN}s…"; sleep "$DOWN"
  state=$(docker inspect -f '{{.State.Status}}' "$C")
  echo "      Состояние после ручного stop: $state (restart-policy его не трогает — это ожидаемо)"
  echo "[4/5] docker start $C"; docker start "$C" >/dev/null
else
  echo "[3/5] Ждём, пока restart-policy сама поднимет контейнер"
  t=0; while [ "$t" -lt 120 ]; do
    [ "$(docker inspect -f '{{.State.Status}}' "$C")" = running ] && [ "$(restarts_of "$C")" -gt "$R0" ] && break
    sleep 2; t=$((t + 2))
  done
  [ "$(restarts_of "$C")" -gt "$R0" ] || { echo "FAIL (б): RestartCount не вырос — restart-policy не сработала"; exit 1; }
  echo "      OK (б1): контейнер перезапущен policy (RestartCount $R0 → $(restarts_of "$C"))"
  echo "[4/5] Ждём возврата статуса в 1"
fi

wait_for "$VIA" "$QUERY" 1 240 || { echo "FAIL (б): статус не вернулся в 1"; exit 1; }
echo "      OK (б): сервис восстановлен, дашборд снова зелёный"

echo "[5/5] Подтверждаем, что «красная» полоса была на графике"
ELAPSED=$(( $(date +%s) - START + 30 ))
if [ "$VIA" = graf ]; then lowest=$(gval "min_over_time(${QUERY}%5B${ELAPSED}s%5D)"); else lowest=$(pval "min_over_time(${QUERY}%5B${ELAPSED}s%5D)"); fi
if [ "$lowest" = 0 ]; then echo "      OK (а): за время теста статус опускался до 0"
else echo "      WARN: провал был короче интервала опроса (5s) и мог не попасть в данные; для гарантии используйте режим stop"; fi
echo "ИТОГ: chaos-тест ($TARGET/$MODE) пройден"
