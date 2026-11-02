#!/bin/sh
# Генерирует .env со случайными паролями (hex — без спецсимволов, безопасно для `source`).
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then echo ".env уже существует — не перезаписываю"; exit 0; fi
r() { openssl rand -hex 16; }
cat > .env <<ENV
MARIADB_ROOT_PASSWORD=$(r)
MARIADB_DATABASE=kuma
MARIADB_USER=kuma
MARIADB_PASSWORD=$(r)
EXPORTER_DB_PASSWORD=$(r)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$(r)
ENV
chmod 600 .env
echo ".env создан. Пароль Grafana: $(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2)"
