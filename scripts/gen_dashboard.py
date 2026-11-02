#!/usr/bin/env python3
"""Генератор дашборда grafana/dashboards/safeboard-health.json (запуск: python3 scripts/gen_dashboard.py)."""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
CONT = 'name=~".*safeboard-.+"'
_id = 0


def target(expr, legend="", instant=False):
    return {"refId": "A", "datasource": DS, "expr": expr, "legendFormat": legend, "instant": instant}


def status_stat(title, expr, x, y, w=4, h=4, ok_text="OK", bad_text="ВСЁ ПЛОХО"):
    """Плитка статуса: 1 → зелёная, 0 → красная «ВСЁ ПЛОХО»."""
    global _id; _id += 1
    return {
        "id": _id, "type": "stat", "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": {
            "mappings": [{"type": "value", "options": {
                "0": {"text": bad_text, "color": "red", "index": 0},
                "1": {"text": ok_text, "color": "green", "index": 1}}}],
            "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
            "color": {"mode": "thresholds"}, "noValue": "НЕТ ДАННЫХ"}, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "textMode": "value",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }


def value_stat(title, expr, unit, x, y, w=4, h=4, legend=""):
    global _id; _id += 1
    return {
        "id": _id, "type": "stat", "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": unit, "noValue": "—",
                                     "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                                     "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"colorMode": "value", "graphMode": "area", "textMode": "value",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }


def ts(title, exprs, unit, x, y, w=12, h=8, minv=None, maxv=None):
    """Временной ряд. exprs: список (expr, legend)."""
    global _id; _id += 1
    tg = []
    for i, (e, l) in enumerate(exprs):
        t = target(e, l); t["refId"] = chr(65 + i); tg.append(t)
    d = {"unit": unit, "custom": {"fillOpacity": 10, "lineWidth": 1}}
    if minv is not None: d["min"] = minv
    if maxv is not None: d["max"] = maxv
    return {"id": _id, "type": "timeseries", "title": title, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": tg,
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                        "tooltip": {"mode": "multi"}}}


def row(title, y):
    global _id; _id += 1
    return {"id": _id, "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}


panels = [
    row("Статус контура", 0),
    status_stat("ОБЩИЙ СТАТУС", "safeboard:overall_up", 0, 1, w=6),
    status_stat("Uptime Kuma", "safeboard:kuma_up", 6, 1, w=4, bad_text="DOWN", ok_text="UP"),
    status_stat("MariaDB", "safeboard:mariadb_up", 10, 1, w=4, bad_text="DOWN", ok_text="UP"),
    value_stat("Latency Kuma", 'probe_duration_seconds{instance="http://safeboard-kuma:3001"}', "s", 14, 1),
    value_stat("Аптайм контейнера Kuma", 'time() - container_start_time_seconds{name="safeboard-kuma"}', "s", 18, 1),
    value_stat("Аптайм контейнера MariaDB", 'time() - container_start_time_seconds{name="safeboard-mariadb"}', "s", 22, 1, w=2),
    ts("Общий статус во времени (1 = OK, 0 = ВСЁ ПЛОХО)",
       [("safeboard:overall_up", "overall"), ("safeboard:kuma_up", "kuma"), ("safeboard:mariadb_up", "mariadb")],
       "none", 0, 5, w=24, h=6, minv=0, maxv=1),

    row("Ресурсы контейнеров (cAdvisor)", 11),
    ts("CPU контейнеров, % одного ядра", [(f"sum by (name) (rate(container_cpu_usage_seconds_total{{{CONT}}}[1m])) * 100", "{{name}}")], "percent", 0, 12),
    ts("RAM контейнеров (working set)", [(f"sum by (name) (container_memory_working_set_bytes{{{CONT}}})", "{{name}}")], "bytes", 12, 12),
    ts("Сеть: приём, байт/с", [(f"sum by (name) (rate(container_network_receive_bytes_total{{{CONT}}}[1m]))", "{{name}}")], "Bps", 0, 20),
    ts("Сеть: отправка, байт/с", [(f"sum by (name) (rate(container_network_transmit_bytes_total{{{CONT}}}[1m]))", "{{name}}")], "Bps", 12, 20),

    row("Хост (node-exporter)", 28),
    ts("CPU хоста, %", [('100 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100', "cpu")], "percent", 0, 29, w=8, h=7, minv=0, maxv=100),
    ts("RAM хоста, %", [("(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100", "ram")], "percent", 8, 29, w=8, h=7, minv=0, maxv=100),
    ts("Диск /, % занято", [('max(100 - node_filesystem_avail_bytes{mountpoint="/",fstype!="rootfs"} / node_filesystem_size_bytes{mountpoint="/",fstype!="rootfs"} * 100)', "disk")], "percent", 16, 29, w=8, h=7, minv=0, maxv=100),

    row("MariaDB (mysqld-exporter)", 36),
    ts("Подключения", [("mysql_global_status_threads_connected", "connected"), ("mysql_global_status_threads_running", "running")], "short", 0, 37),
    ts("Запросы в секунду", [("rate(mysql_global_status_queries[1m])", "queries/s")], "ops", 12, 37),

    row("Доступность и latency веб-сервисов (blackbox)", 45),
    ts("Latency проб, сек", [("probe_duration_seconds", "{{instance}}")], "s", 0, 46),
    ts("probe_success (1 = доступен)", [("probe_success", "{{instance}}")], "none", 12, 46, minv=0, maxv=1),
]

dash = {
    "uid": "safeboard-health", "title": "Safeboard — здоровье контура", "tags": ["safeboard"],
    "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": True,
    "refresh": "5s", "time": {"from": "now-15m", "to": "now"}, "panels": panels,
}
out = Path(__file__).resolve().parent.parent / "grafana" / "dashboards" / "safeboard-health.json"
out.write_text(json.dumps(dash, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("written", out)
