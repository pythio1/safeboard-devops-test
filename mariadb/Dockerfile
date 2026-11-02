FROM mariadb:11.4
# Скрипты из этой папки выполняются ОДИН раз — при первой инициализации пустого тома.
COPY --chmod=0755 init/ /docker-entrypoint-initdb.d/
