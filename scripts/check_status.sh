#!/bin/sh
# Валидация всей платформы: контейнеры + метрики Prometheus + доказательство, что Kuma работает на MariaDB.
# Код возврата 0 = всё хорошо. Использование: check_status.sh [таймаут_сек]
. "$(dirname "$0")/lib.sh"
TIMEOUT="${1:-180}"
fail=0

echo "== Контейнеры =="
print_containers
for c in safeboard-mariadb safeboard-kuma safeboard-prometheus safeboard-grafana; do
  case "$(health_of "$c")" in running/healthy|running/no-healthcheck) ;; *) echo "ПРОБЛЕМА: $c не healthy"; fail=1 ;; esac
done

echo "== Метрики (ждём до ${TIMEOUT}s) =="
check() {  # <название> <запрос>
  if wait_for prom "$2" 1 "$TIMEOUT"; then echo "  OK   $1"; else echo "  FAIL $1 (запрос: $2)"; fail=1; fi
}
check "все scrape-targets подняты (min(up) == 1)" "min(up)"
check "MariaDB доступна (safeboard:mariadb_up)"   "safeboard:mariadb_up"
check "Uptime Kuma отвечает (safeboard:kuma_up)"  "safeboard:kuma_up"
check "общий статус (safeboard:overall_up)"       "safeboard:overall_up"

echo "== Targets, которые НЕ в состоянии UP =="
down=$(prom_q 'up%3D%3D0' | grep -o '"job":"[^"]*"' | sort -u)
if [ -n "$down" ]; then echo "$down"; fail=1; else echo "  нет — все targets UP"; fi

echo "== Uptime Kuma действительно использует MariaDB =="
t=0; tables=0
while [ "$t" -lt 120 ]; do
  tables=$(docker exec safeboard-mariadb sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -D "$MARIADB_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()"' 2>/dev/null | tr -d '\r')
  [ "${tables:-0}" -gt 0 ] 2>/dev/null && break
  sleep 3; t=$((t + 3))
done
if [ "${tables:-0}" -gt 0 ] 2>/dev/null; then echo "  OK   в БД Kuma таблиц: $tables (Kuma пишет в MariaDB)"
else echo "  FAIL в БД Kuma нет таблиц — интеграция НЕ подтверждена. Смотрите: docker logs safeboard-kuma"; fail=1; fi
if docker logs safeboard-kuma 2>&1 | grep -qi 'SQLite Version'; then
  echo "  WARN в логах Kuma есть строка про SQLite — убедитесь, что используется образ :2 и заданы UPTIME_KUMA_DB_*"
fi

echo "== Метрики контейнеров cAdvisor (нужны панелям CPU/RAM) =="
n=$(pval 'count(container_cpu_usage_seconds_total%7Bname%3D~%22.*safeboard-.%2B%22%7D)')
if [ "${n:-0}" != 0 ] && [ -n "$n" ]; then echo "  OK   cAdvisor отдаёт метрики $n контейнеров"
else echo "  WARN cAdvisor не отдаёт label name (типично для Docker Desktop). Панели CPU/RAM контейнеров будут пустыми; проверьте в Prometheus: container_cpu_usage_seconds_total"; fi

[ "$fail" -eq 0 ] && echo "ИТОГ: платформа здорова" || echo "ИТОГ: есть проблемы"
exit "$fail"
