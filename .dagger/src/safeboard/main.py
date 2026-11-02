"""Safeboard — Dagger-модуль управления локальным контуром мониторинга Uptime Kuma.

Принцип: Dagger НЕ запускает контейнеры стенда сам. Он запускает одноразовый контейнер `docker:cli`,
пробрасывает в него сокет Docker-демона хоста и внутри выполняет `docker compose ...`.
Поэтому стенд живёт на хосте (виден в `docker ps`), а Dagger отвечает за повторяемый запуск.

Пароли (.env) передаются явным аргументом-секретом `--env-file=file:.env` и монтируются в контейнер как /src/.env.
Так мы НЕ зависим от того, попадёт ли .env (он в .gitignore) в загружаемую директорию репозитория.

Все функции с побочными эффектами помечены cache="never": иначе Dagger (>=0.19.4) вернул бы
закэшированный результат и ничего бы не выполнил при повторном вызове.
"""
import time
from typing import Annotated

import dagger
from dagger import DefaultPath, Doc, Ignore, dag, function, object_type

DOCKER_CLI_IMAGE = "docker:28-cli"      # содержит docker CLI + плагин compose
NETWORK = "safeboard-net"               # общая сеть двух слоёв
GRAFANA_ALIAS = "grafana"               # имя, под которым Grafana видна внутри функции configure-grafana
IGNORE = [".git", ".dagger/sdk", "**/__pycache__", "*.zip"]


def _docker_cli(src: dagger.Directory, sock: dagger.Socket, env_file: dagger.Secret) -> dagger.Container:
    """Контейнер с docker CLI, репозиторием в /src, .env (секрет) в /src/.env и сокетом хоста."""
    return (
        dag.container()
        .from_(DOCKER_CLI_IMAGE)
        .with_unix_socket("/var/run/docker.sock", sock)
        .with_directory("/src", src)
        .with_mounted_secret("/src/.env", env_file)
        .with_workdir("/src")
    )


async def _sh(ctr: dagger.Container, script: str) -> str:
    """Выполнить shell-скрипт и вернуть вывод. CACHEBUSTER гарантирует, что слой не возьмётся из кэша."""
    pre = (
        "exec 2>&1\n"
        # Явная проверка: .env реально на месте и не пуст (иначе compose упадёт с невнятной ошибкой).
        'test -s /src/.env || { echo "ОШИБКА: /src/.env пуст или отсутствует. '
        'Запустите ./scripts/init-env.sh и передайте --env-file=file:.env"; exit 1; }\n'
    )
    ctr = ctr.with_env_variable("CACHEBUSTER", str(time.time_ns()))
    return await ctr.with_exec(["sh", "-ec", pre + script]).stdout()


def _compose(file: str) -> str:
    """Валидация конфигурации (YAML, переменные), затем запуск."""
    return f"""
docker network inspect {NETWORK} >/dev/null 2>&1 || docker network create {NETWORK}
echo "== docker compose config ({file}) =="
docker compose --env-file .env -f {file} config -q && echo "конфигурация валидна"
docker compose --env-file .env -f {file} up -d --build --wait --wait-timeout 300
echo
docker compose --env-file .env -f {file} ps
"""


@object_type
class Safeboard:
    @function(cache="never")
    async def deploy_app(
        self,
        docker_sock: Annotated[dagger.Socket, Doc("Сокет Docker-демона хоста: /var/run/docker.sock")],
        env_file: Annotated[dagger.Secret, Doc("Файл с паролями: file:.env")],
        src: Annotated[dagger.Directory, DefaultPath("/"), Ignore(IGNORE), Doc("Корень репозитория (определяется автоматически)")],
    ) -> str:
        """Слой 1: поднимает MariaDB и Uptime Kuma, связывает их (общая сеть + переменные окружения)."""
        script = _compose("docker-compose.app.yml") + \
            'echo\necho "Uptime Kuma: http://localhost:3001  (при первом входе создайте admin-пользователя)"\n'
        return await _sh(_docker_cli(src, docker_sock, env_file), script)

    @function(cache="never")
    async def deploy_monitoring(
        self,
        docker_sock: Annotated[dagger.Socket, Doc("Сокет Docker-демона хоста")],
        env_file: Annotated[dagger.Secret, Doc("Файл с паролями: file:.env")],
        src: Annotated[dagger.Directory, DefaultPath("/"), Ignore(IGNORE)],
    ) -> str:
        """Слой 2: поднимает Prometheus, Grafana и экспортёры (node, cAdvisor, mysqld, blackbox)."""
        script = _compose("docker-compose.monitoring.yml") + \
            'echo\necho "Grafana: http://localhost:3000   Prometheus: http://localhost:9090"\n'
        return await _sh(_docker_cli(src, docker_sock, env_file), script)

    @function(cache="never")
    async def configure_grafana(
        self,
        grafana: Annotated[dagger.Service, Doc("Grafana на хосте: tcp://localhost:3000")],
        env_file: Annotated[dagger.Secret, Doc("Файл с паролями: file:.env (берём GRAFANA_ADMIN_USER/PASSWORD)")],
        src: Annotated[dagger.Directory, DefaultPath("/"), Ignore(IGNORE)],
    ) -> str:
        """Через HTTP API Grafana создаёт data source Prometheus и загружает дашборды из grafana/."""
        ctr = (
            dag.container()
            .from_("python:3.13-alpine")
            .with_service_binding(GRAFANA_ALIAS, grafana)   # Grafana с хоста доступна как http://grafana:3000
            .with_directory("/src", src)
            .with_mounted_secret("/src/.env", env_file)     # пароль читается скриптом из секрета
            .with_env_variable("GRAFANA_URL", f"http://{GRAFANA_ALIAS}:3000")
            .with_env_variable("REPO_DIR", "/src")
            .with_env_variable("CACHEBUSTER", str(time.time_ns()))
            .with_exec(["python", "/src/scripts/configure_grafana.py"])
        )
        return await ctr.stdout()

    @function(cache="never")
    async def check_status(
        self,
        docker_sock: Annotated[dagger.Socket, Doc("Сокет Docker-демона хоста")],
        env_file: Annotated[dagger.Secret, Doc("Файл с паролями: file:.env")],
        src: Annotated[dagger.Directory, DefaultPath("/"), Ignore(IGNORE)],
    ) -> str:
        """Проверяет контейнеры, метрики, targets и что Kuma реально работает на MariaDB. Падает, если что-то не так."""
        return await _sh(_docker_cli(src, docker_sock, env_file), "sh scripts/check_status.sh 180")

    @function(cache="never")
    async def deploy_all(
        self,
        docker_sock: Annotated[dagger.Socket, Doc("Сокет Docker-демона хоста")],
        env_file: Annotated[dagger.Secret, Doc("Файл с паролями: file:.env")],
        grafana: Annotated[dagger.Service, Doc("Grafana на хосте: tcp://localhost:3000")],
        src: Annotated[dagger.Directory, DefaultPath("/"), Ignore(IGNORE)],
    ) -> str:
        """БОНУС: поднимает всю платформу целиком, настраивает Grafana и валидирует статус всех систем."""
        out = [
            "### deploy-app\n" + await self.deploy_app(docker_sock, env_file, src),
            "### deploy-monitoring\n" + await self.deploy_monitoring(docker_sock, env_file, src),
            "### configure-grafana\n" + await self.configure_grafana(grafana, env_file, src),
            "### check-status\n" + await self.check_status(docker_sock, env_file, src),
        ]
        return "\n".join(out)

    @function(cache="never")
    async def chaos(
        self,
        docker_sock: Annotated[dagger.Socket, Doc("Сокет Docker-демона хоста")],
        env_file: Annotated[dagger.Secret, Doc("Файл с паролями: file:.env")],
        src: Annotated[dagger.Directory, DefaultPath("/"), Ignore(IGNORE)],
        target: Annotated[str, Doc("Что ломаем: mariadb или kuma")] = "mariadb",
        mode: Annotated[str, Doc("kill — проверка restart-policy; stop — ручная остановка + ручной старт")] = "kill",
    ) -> str:
        """БОНУС: Chaos-тест — роняет контейнер и проверяет красный статус на дашборде и восстановление."""
        if target not in ("mariadb", "kuma") or mode not in ("kill", "stop"):
            raise ValueError("target: mariadb|kuma, mode: kill|stop")
        return await _sh(_docker_cli(src, docker_sock, env_file), f"sh scripts/chaos.sh {target} {mode} 25")
