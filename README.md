# Safeboard — локальный отказоустойчивый контур мониторинга Uptime Kuma

Локальный стенд мониторинга из двух независимых Docker Compose-слоёв, которыми управляет **Dagger**.

| Слой | Состав | Файл |
|---|---|---|
| 1. Приложение и БД | Uptime Kuma 2.x + MariaDB 11.4 | `docker-compose.app.yml` |
| 2. Наблюдаемость | Prometheus, Grafana, node-exporter, cAdvisor, mysqld-exporter, blackbox-exporter | `docker-compose.monitoring.yml` |

## Архитектура

```text
Хост
  │
  ├── Docker socket
  │
  ▼
Dagger CLI
  │
  ▼
Dagger-функции
  │
  └── docker:cli
        │
        └── docker compose
              │
              ├── safeboard-net
              │     ├── Uptime Kuma
              │     ├── MariaDB
              │     ├── Prometheus
              │     ├── Grafana
              │     ├── node-exporter
              │     ├── cAdvisor
              │     ├── mysqld-exporter
              │     └── blackbox-exporter
              │
              └── Grafana API — настройка datasource и dashboard
```

Uptime Kuma использует MariaDB для хранения данных. Prometheus собирает метрики приложения, базы данных, экспортёров и проверок доступности. Grafana отображает собранные данные на дашборде.

## 1. Требования

- Linux, macOS или Windows 10/11 с WSL2.
- Docker Engine или Docker Desktop.
- Docker Compose V2.
- Dagger CLI.
- Свободные порты:
  - `3001` — Uptime Kuma;
  - `3000` — Grafana;
  - `9090` — Prometheus.

Проверить установленные инструменты:

```bash
docker version
docker compose version
dagger version
```

Установить Dagger на macOS или Linux:

```bash
curl -fsSL https://dl.dagger.io/dagger/install.sh | BIN_DIR=$HOME/.local/bin sh
export PATH=$HOME/.local/bin:$PATH
```

Для Windows рекомендуется использовать WSL2 и выполнять команды внутри терминала Linux.

**Особенности macOS и Docker Desktop**

На macOS Docker Desktop запускает контейнеры внутри Linux-виртуальной машины. Поэтому node-exporter показывает метрики Linux-виртуальной машины, а не непосредственно macOS. cAdvisor также может предоставлять неполный набор метрик контейнеров.

Полнота метрик CPU/RAM контейнеров не гарантируется на Docker Desktop. Основной сценарий для получения полного набора метрик — Linux с Docker Engine.

## 2. Подготовка окружения

Все команды необходимо выполнять из корневой папки проекта.

Сделать скрипты исполняемыми:

```bash
chmod +x scripts/*.sh
```

Создать файл окружения со случайными паролями:

```bash
./scripts/init-env.sh
```

Альтернативный вариант:

```bash
cp .env.example .env
```

При использовании второго способа необходимо заполнить значения переменных в `.env`.

Проверить окружение:

```bash
bash scripts/preflight.sh
```

Проверить доступные функции Dagger:

```bash
dagger functions
```

Модуль должен обнаружить шесть функций:

- `deploy-app`
- `deploy-monitoring`
- `configure-grafana`
- `check-status`
- `deploy-all`
- `chaos`

### Важные параметры запуска Dagger

В этом проекте используется параметр `--src=.`. Он явно передаёт текущую папку проекта в Dagger.

Рекомендуется всегда запускать команды из корня проекта и указывать этот параметр. На macOS он также помогает избежать попыток Dagger прочитать лишние директории домашнего каталога.

Docker socket передаётся так:

```bash
--docker-sock=unix:///var/run/docker.sock
```

Файл `.env` передаётся в Dagger как Secret:

```bash
--env-file=file:.env
```

Файл `.env` исключён из Git через `.gitignore`. Не публикуйте его и не добавляйте в архив для сдачи.

## 3. Запуск платформы

### Шаг 1. Развернуть приложение и базу данных

```bash
dagger call deploy-app \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env
```

Команда проверяет Compose-конфигурацию и запускает:

- Uptime Kuma;
- MariaDB.

Дождитесь завершения команды и статуса `healthy` у основных контейнеров.

Uptime Kuma:

http://localhost:3001

При первом входе создайте администратора.

### Шаг 2. Развернуть мониторинг

```bash
dagger call deploy-monitoring \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env
```

Команда запускает:

- Prometheus;
- Grafana;
- node-exporter;
- cAdvisor;
- mysqld-exporter;
- blackbox-exporter.

### Шаг 3. Настроить Grafana

```bash
dagger call configure-grafana \
  --src=. \
  --grafana=tcp://localhost:3000 \
  --env-file=file:.env
```

Команда автоматически:

1. Проверяет доступность Grafana.
2. Создаёт или обновляет источник данных Prometheus.
3. Загружает дашборд Safeboard.
4. Проверяет подключение к Prometheus.

После успешного выполнения дашборд доступен по адресу:

http://localhost:3000/d/safeboard-health

## 4. Бонус: полный запуск одной командой

Для развёртывания всей платформы и автоматической проверки можно использовать:

```bash
dagger call deploy-all \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env \
  --grafana=tcp://localhost:3000
```

Команда последовательно выполняет:

1. `deploy-app`;
2. `deploy-monitoring`;
3. `configure-grafana`;
4. `check-status`.

Эта команда была успешно проверена на macOS с Docker Desktop.

## 5. Проверка состояния платформы

Запустить отдельную проверку:

```bash
dagger call check-status \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env
```

Проверка включает:

- состояние контейнеров;
- состояние Prometheus scrape-targets;
- доступность MariaDB;
- доступность Uptime Kuma;
- общий статус платформы;
- наличие таблиц Uptime Kuma в MariaDB;
- наличие метрик cAdvisor, необходимых для панелей CPU/RAM.

Успешный результат должен содержать сообщения:

```text
OK все scrape-targets подняты (min(up) == 1)
OK MariaDB доступна
OK Uptime Kuma отвечает
OK общий статус
нет — все targets UP
OK в БД Kuma таблиц: ...
ИТОГ: платформа здорова
```

Для проверки MariaDB используется наличие таблиц Kuma. Это позволяет подтвердить, что приложение действительно работает с MariaDB.

### Результат фактической проверки на macOS

В ходе запуска проекта были успешно выполнены:

- `deploy-app`;
- `deploy-monitoring`;
- `configure-grafana`;
- `check-status`;
- `deploy-all`.

Контейнеры MariaDB, Uptime Kuma, Prometheus, Grafana и cAdvisor получили статус `healthy`. Остальные экспортёры работали в состоянии `running`.

Все Prometheus targets были в состоянии `UP`. Проверка подтвердила доступность MariaDB и Uptime Kuma, а также наличие 28 таблиц базы данных Kuma.

Было обнаружено ограничение cAdvisor: на Docker Desktop для macOS отсутствует label `name` в метриках контейнеров. Поэтому панели CPU/RAM контейнеров могут быть пустыми, хотя сам cAdvisor работает и target находится в состоянии `UP`.

Это ограничение среды Docker Desktop, а не отказ всей платформы.

## 6. Адреса сервисов

| Сервис | Адрес | Доступ |
|---|---|---|
| Uptime Kuma | http://localhost:3001 | Администратор создаётся при первом входе |
| Grafana | http://localhost:3000 | `admin`, пароль из `GRAFANA_ADMIN_PASSWORD` в `.env` |
| Дашборд Safeboard | http://localhost:3000/d/safeboard-health | Через Grafana |
| Prometheus | http://localhost:9090 | Status → Targets, Alerts |

В Prometheus на странице Status → Targets можно проверить состояние всех целей сбора метрик.

## 7. Проверка сохранности данных

Данные MariaDB и Uptime Kuma хранятся в Docker volumes.

Проверить volumes:

```bash
docker volume ls
```

Перезапустить контейнеры:

```bash
docker restart safeboard-mariadb safeboard-kuma
```

После перезапуска проверьте, что Uptime Kuma открывается и ранее созданный пользователь сохранился.

Не используйте `docker compose down -v`, если хотите сохранить данные.

## 8. Chaos-тестирование (бонус)

В проекте предусмотрена функция `chaos` для проверки поведения платформы при отказе сервиса.

Перед выполнением теста убедитесь, что платформа полностью запущена и работает.

### Имитация аварийного завершения MariaDB

```bash
dagger call chaos \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env \
  --target=mariadb \
  --mode=kill
```

### Имитация аварийного завершения Uptime Kuma

```bash
dagger call chaos \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env \
  --target=kuma \
  --mode=kill
```

### Ручная остановка MariaDB

```bash
dagger call chaos \
  --src=. \
  --docker-sock=unix:///var/run/docker.sock \
  --env-file=file:.env \
  --target=mariadb \
  --mode=stop
```

**Разница между `kill` и `stop`:**

- `docker kill` имитирует аварийное завершение контейнера. Docker restart-policy может автоматически перезапустить его.
- `docker stop` выполняет штатную ручную остановку. Docker не перезапускает вручную остановленный контейнер автоматически.

Поэтому режим `kill` используется для проверки restart-policy, а режим `stop` — для проверки обнаружения отказа и последующего восстановления после ручного запуска.

Во время тестирования можно открыть дашборд Grafana и наблюдать изменение общего статуса.

## 9. Особенности поддержки платформ

| Платформа | Особенности |
|---|---|
| Linux + Docker Engine | Основная целевая среда. Наиболее полный набор метрик |
| Windows + WSL2 | Основные сервисы работают; полноту метрик необходимо проверить |
| macOS + Docker Desktop | Основные сервисы работают; node-exporter показывает Linux VM, метрики cAdvisor могут быть неполными |

Если панели CPU/RAM контейнеров пустые, откройте Prometheus и выполните запрос:

```promql
container_cpu_usage_seconds_total
```

Проверьте, присутствует ли label `name` у возвращаемых временных рядов.

Если label отсутствует, панели, использующие этот label, не смогут отобразить данные. Остальные проверки доступности и метрики MariaDB от этого не зависят.

## 10. Остановка и очистка

Остановить слой мониторинга без удаления данных:

```bash
docker compose --env-file .env -f docker-compose.monitoring.yml down
```

Остановить приложение и MariaDB без удаления данных:

```bash
docker compose --env-file .env -f docker-compose.app.yml down
```

Удалить данные мониторинга:

```bash
docker compose --env-file .env -f docker-compose.monitoring.yml down -v
```

Удалить данные приложения и MariaDB:

```bash
docker compose --env-file .env -f docker-compose.app.yml down -v
```

Удалить общую Docker-сеть после остановки всех сервисов:

```bash
docker network rm safeboard-net
```

**Внимание:** команды с `-v` удаляют volumes и хранящиеся в них данные. Используйте их только если действительно хотите полностью очистить стенд.

## 11. Проектные решения

### Dagger и Docker socket

Dagger-функции запускают Docker CLI внутри контейнера `docker:cli`. Docker socket передаётся из хостовой системы, поэтому контейнеры создаются Docker-демоном хоста и остаются работать после завершения `dagger call`.

### Конфигурации сервисов

Конфигурации Prometheus и MariaDB включаются в соответствующие образы через `build:`. Это позволяет избежать проблем с bind mount путями, когда Compose запускается из контейнера Dagger, а Docker демон работает на хосте.

Grafana настраивается через API.

### Секреты

Пароли хранятся в `.env`. Файл исключён из Git через `.gitignore` и передаётся Dagger как Secret через `--env-file=file:.env`.

В Compose используются обязательные переменные окружения, чтобы запуск без необходимых секретов завершался с понятной ошибкой.

### MariaDB

MariaDB не публикует порт базы данных наружу. Для mysqld-exporter используется отдельная учётная запись с необходимыми правами.

### Кэширование Dagger

Функции, выполняющие операции с побочными эффектами, настроены так, чтобы повторный вызов действительно выполнял команды развёртывания, а не возвращал только закэшированный результат.

### Общий статус

Общий статус платформы вычисляется recording rule в Prometheus:

```promql
overall_up = mariadb_up * kuma_up
```

Если одна из основных систем недоступна, общий статус становится `0`.

## 12. Структура проекта

```text
.
├── .dagger/
│   └── src/
│       └── safeboard/
│           └── main.py
├── dagger.json
├── docker-compose.app.yml
├── docker-compose.monitoring.yml
├── mariadb/
├── prometheus/
├── grafana/
├── scripts/
├── .env.example
├── .gitignore
├── README.md
└── AI_REVIEW.md
```

Основные компоненты:

- `.dagger/` — Dagger-модуль на Python;
- `docker-compose.app.yml` — приложение и база данных;
- `docker-compose.monitoring.yml` — мониторинг и экспортёры;
- `mariadb/` — Dockerfile и скрипты инициализации MariaDB;
- `prometheus/` — конфигурация сбора метрик и правил;
- `grafana/` — datasource и dashboard;
- `scripts/` — скрипты подготовки окружения, проверки, настройки Grafana и Chaos-тестирования;
- `.env.example` — пример переменных окружения без реальных паролей;
- `AI_REVIEW.md` — отчёт об использовании AI.

## 13. Что не реализовано

Galera Cluster с тремя узлами MariaDB и HAProxy не реализован.

В текущем проекте используется одна нода MariaDB с постоянным Docker volume. Это обеспечивает сохранность данных при перезапуске контейнера, но не является полноценной кластерной отказоустойчивостью базы данных.

Добавление Galera и HAProxy рассматривается как дальнейшее развитие проекта.
