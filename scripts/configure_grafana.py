#!/usr/bin/env python3
"""Настройка Grafana через HTTP API: data source + дашборды. Идемпотентно (можно запускать повторно).

Логин/пароль берутся из /src/.env (GRAFANA_ADMIN_USER/PASSWORD) или из GRAFANA_USER/GRAFANA_PASSWORD.
Переменные окружения: GRAFANA_URL, REPO_DIR (по умолчанию /src).
Только стандартная библиотека — отдельных зависимостей ставить не нужно.
"""
import base64, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

URL = os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")
REPO = Path(os.environ.get("REPO_DIR", "/src"))


def load_env(path):
    """Мини-парсер .env (KEY=VALUE, без кавычек и экспорта). Секрет монтируется Dagger-ом как файл."""
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


_env = load_env(REPO / ".env")
USER = os.environ.get("GRAFANA_USER") or _env.get("GRAFANA_ADMIN_USER", "admin")
PASSWORD = os.environ.get("GRAFANA_PASSWORD") or _env.get("GRAFANA_ADMIN_PASSWORD")
if not PASSWORD:
    sys.exit("ОШИБКА: нет пароля Grafana (передайте --env-file=file:.env)")
AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers={"Authorization": AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode() or "null"
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: return e.code, json.loads(raw)
        except ValueError: return e.code, raw


def wait_ready(tries=60):
    for _ in range(tries):
        try:
            st, body = call("GET", "/api/health")
            if st == 200 and isinstance(body, dict) and body.get("database") == "ok":
                print("Grafana готова:", body); return
        except Exception as e:  # соединение ещё не поднялось
            last = e
        time.sleep(2)
    sys.exit("ОШИБКА: Grafana не ответила на /api/health за 2 минуты")


def upsert_datasource(ds):
    st, existing = call("GET", f"/api/datasources/uid/{ds['uid']}")
    if st == 200:
        ds = {**ds, "id": existing["id"]}
        st, body = call("PUT", f"/api/datasources/{existing['id']}", ds)
        action = "обновлён"
    else:
        st, body = call("POST", "/api/datasources", ds)
        action = "создан"
    if st not in (200, 201):
        sys.exit(f"ОШИБКА data source {ds['name']}: {st} {body}")
    print(f"Data source «{ds['name']}» {action}")


def import_dashboard(path):
    dash = json.loads(path.read_text(encoding="utf-8"))
    dash["id"] = None  # id назначает сама Grafana; идентичность — по uid
    st, body = call("POST", "/api/dashboards/db", {"dashboard": dash, "overwrite": True, "message": "configure-grafana"})
    if st != 200:
        sys.exit(f"ОШИБКА дашборд {path.name}: {st} {body}")
    print(f"Дашборд «{dash['title']}» загружен: {URL}{body.get('url', '')}")


def main():
    wait_ready()
    for f in sorted((REPO / "grafana" / "datasources").glob("*.json")):
        upsert_datasource(json.loads(f.read_text(encoding="utf-8")))
    for f in sorted((REPO / "grafana" / "dashboards").glob("*.json")):
        import_dashboard(f)
    # Проверка связки Grafana → Prometheus
    st, body = call("GET", "/api/datasources/uid/prometheus/health")
    print("Проверка data source:", st, body if st != 200 else body.get("message", body))
    if st != 200:
        sys.exit("ОШИБКА: Grafana не достучалась до Prometheus (запущен ли deploy-monitoring?)")
    st, found = call("GET", "/api/search?query=Safeboard")
    if st != 200 or not found:
        sys.exit("ОШИБКА: дашборд не найден после импорта")
    print("Готово: найдено дашбордов:", len(found))


if __name__ == "__main__":
    main()
