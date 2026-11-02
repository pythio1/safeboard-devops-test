#!/bin/sh
# Общие функции для check_status.sh и chaos.sh. Выполняются внутри контейнера docker:cli
# с пробросом сокета хоста, поэтому `docker exec` работает с контейнерами хоста.

[ -f /src/.env ] && { set -a; . /src/.env; set +a; }

PROM=safeboard-prometheus
GRAF=safeboard-grafana

# Запрос в Prometheus напрямую (через wget внутри контейнера Prometheus).
prom_q() { docker exec "$PROM" wget -qO- "http://localhost:9090/api/v1/query?query=$1" 2>/dev/null; }
# Запрос ЧЕРЕЗ Grafana (data source proxy) — именно то, что видит дашборд.
graf_q() {
  auth=$(printf '%s:%s' "${GRAFANA_ADMIN_USER:-admin}" "${GRAFANA_ADMIN_PASSWORD:-}" | base64 | tr -d '\n')
  docker exec "$GRAF" wget -qO- --header="Authorization: Basic $auth" \
    "http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query?query=$1" 2>/dev/null
}
# Достаёт значение из JSON-ответа instant-запроса (пусто, если данных нет).
extract() { sed -n 's/.*"value":\[[0-9.]*,"\([^"]*\)"\].*/\1/p'; }
pval() { prom_q "$1" | extract; }
gval() { graf_q "$1" | extract; }

# wait_for <prom|graf> <запрос> <ожидаемое значение> <таймаут, сек>
wait_for() {
  fn=$1; q=$2; want=$3; timeout=$4; t=0
  while [ "$t" -lt "$timeout" ]; do
    if [ "$fn" = graf ]; then v=$(gval "$q"); else v=$(pval "$q"); fi
    [ "$v" = "$want" ] && return 0
    sleep 2; t=$((t + 2))
  done
  return 1
}

health_of() { docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$1" 2>/dev/null || echo "missing"; }
restarts_of() { docker inspect -f '{{.RestartCount}}' "$1" 2>/dev/null || echo 0; }

print_containers() {
  for c in safeboard-mariadb safeboard-kuma safeboard-prometheus safeboard-grafana \
           safeboard-node-exporter safeboard-cadvisor safeboard-mysqld-exporter safeboard-blackbox; do
    printf '  %-28s %s\n' "$c" "$(health_of "$c")"
  done
}
