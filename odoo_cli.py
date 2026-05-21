#!/usr/bin/env python3
"""
Odoo Timesheet CLI — operaciones de partes de horas sin dependencia MCP.

Subcomandos:
    python3 odoo_cli.py list-projects [--refresh]
    python3 odoo_cli.py list-timesheets [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--today]
    python3 odoo_cli.py create --name STR --date YYYY-MM-DD --hours FLOAT --project INT --task INT

Credenciales: carga .env del directorio del script, fallback a env vars ODOO_*.
"""

import os
import re
import sys
import json
import argparse
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
CATALOG_PATH = SCRIPT_DIR / "projects_cache.json"
CATALOG_TTL = timedelta(hours=24)


def _load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and key not in os.environ:
                    os.environ[key] = val


_load_env()

BASE_URL = os.getenv("ODOO_URL", "https://next.edf.global")
USER = os.getenv("ODOO_USER", "")
PASSWORD = os.getenv("ODOO_PASSWORD", "")
EMPLOYEE_ID = int(os.getenv("ODOO_EMPLOYEE_ID", "0"))
DB_NAME = os.getenv("ODOO_DB", "")


class OdooClient:
    _instance = None

    def __init__(self):
        self.session = requests.Session()
        self.uid = 0
        self._id = 0
        self._login()

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _rpc(self, endpoint, params):
        self._id += 1
        r = self.session.post(
            f"{BASE_URL.rstrip('/')}{endpoint}",
            json={"jsonrpc": "2.0", "method": "call", "id": self._id, "params": params},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            msg = data["error"].get("data", {}).get("message", str(data["error"]))
            raise RuntimeError(f"Odoo error: {msg}")
        return data["result"]

    def _login(self):
        db = DB_NAME
        if not db:
            try:
                dbs = self._rpc("/web/database/list", {})
                db = dbs[0] if isinstance(dbs, list) and dbs else ""
            except RuntimeError as e:
                if "Access Denied" in str(e):
                    db = self._detect_db_via_web_login()
                else:
                    raise
        if not db:
            raise RuntimeError(
                "No se pudo determinar el nombre de la base de datos de Odoo. "
                "Configura ODOO_DB o habilita /web/database/list."
            )
        res = self._rpc("/web/session/authenticate", {
            "db": db, "login": USER, "password": PASSWORD
        })
        self.uid = res.get("uid")
        if not self.uid:
            raise RuntimeError("Login fallido. Revisa ODOO_USER / ODOO_PASSWORD.")

    def _detect_db_via_web_login(self):
        session = requests.Session()
        login_page = session.get(f"{BASE_URL.rstrip('/')}/web/login", timeout=30)
        login_page.raise_for_status()
        m = re.search(r'csrf_token:\s*"([^"]+)"', login_page.text)
        csrf = m.group(1) if m else ""
        resp = session.post(
            f"{BASE_URL.rstrip('/')}/web/login",
            data={"csrf_token": csrf, "login": USER, "password": PASSWORD},
            timeout=30,
            allow_redirects=False,
        )
        if resp.status_code not in (200, 302, 303):
            raise RuntimeError(
                f"Login web falló (status {resp.status_code}, esperaba 200/302/303)."
            )
        info = session.post(
            f"{BASE_URL.rstrip('/')}/web/session/get_session_info",
            json={"jsonrpc": "2.0", "method": "call", "id": 1, "params": {}},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        info.raise_for_status()
        data = info.json()
        db = data.get("result", {}).get("db", "")
        if not db:
            raise RuntimeError("No se pudo extraer el nombre de la BD de la sesión web.")
        return db

    def search_read(self, model, domain, fields, limit=500, order="name asc"):
        return self._rpc(
            f"/web/dataset/call_kw/{model}/search_read",
            {"model": model, "method": "search_read", "args": [domain],
             "kwargs": {"fields": fields, "limit": limit, "order": order,
                        "context": {"lang": "es_ES"}}},
        )

    def create(self, model, vals, context=None):
        return self._rpc(
            f"/web/dataset/call_kw/{model}/create",
            {"model": model, "method": "create", "args": [vals],
             "kwargs": {"context": context or {"lang": "es_ES", "tz": "Europe/Madrid",
                                               "allowed_company_ids": [1]}}},
        )

    def read(self, model, ids, fields):
        return self._rpc(
            f"/web/dataset/call_kw/{model}/read",
            {"model": model, "method": "read", "args": [ids],
             "kwargs": {"fields": fields, "context": {}}},
        )


def _refresh_catalog(client):
    projects = client.search_read(
        "project.project", [["active", "=", True]],
        ["id", "name", "analytic_account_id"], limit=500,
    )
    proj_ids = [p["id"] for p in projects]
    tasks = client.search_read(
        "project.task", [["project_id", "in", proj_ids], ["active", "=", True]],
        ["id", "name", "project_id"], limit=2000, order="project_id asc, name asc",
    )
    tasks_by_proj = {}
    for t in tasks:
        tasks_by_proj.setdefault(t["project_id"][0], []).append(
            {"id": t["id"], "name": t["name"]}
        )
    catalog = [
        {"id": p["id"], "name": p["name"],
         "tasks": tasks_by_proj.get(p["id"], [])}
        for p in projects
    ]
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False))
    return catalog


def _get_catalog(client, refresh=False):
    if refresh and CATALOG_PATH.exists():
        CATALOG_PATH.unlink()
    if CATALOG_PATH.exists():
        age = datetime.now() - datetime.fromtimestamp(CATALOG_PATH.stat().st_mtime)
        if age < CATALOG_TTL:
            return json.loads(CATALOG_PATH.read_text())
    return _refresh_catalog(client)


def cmd_list_projects(args):
    client = OdooClient.get()
    catalog = _get_catalog(client, refresh=args.refresh)
    lines = [f"Proyectos activos en Odoo ({len(catalog)} proyectos):\n"]
    for proj in catalog:
        task_str = (
            ", ".join(f"[{t['id']}] {t['name']}" for t in proj["tasks"])
            if proj["tasks"] else "sin tareas"
        )
        lines.append(f"[{proj['id']}] {proj['name']}\n    Tareas: {task_str}")
    print("\n".join(lines))


def cmd_list_timesheets(args):
    client = OdooClient.get()
    date_from = args.date_from or ""
    date_to = args.date_to or ""
    if args.today:
        today = date.today().isoformat()
        date_from = today
        date_to = today

    domain = [
        ["project_id", "!=", False],
        ["user_id", "=", client.uid],
    ]
    if date_from:
        domain.append(["date", ">=", date_from])
    if date_to:
        domain.append(["date", "<=", date_to])

    entries = client.search_read(
        "account.analytic.line",
        domain,
        ["id", "name", "date", "unit_amount", "project_id", "task_id"],
        limit=args.limit,
        order="date desc",
    )

    if not entries:
        print("No se encontraron entradas con los filtros indicados.")
        return

    total = sum(e.get("unit_amount", 0) for e in entries)
    lines = [f"Últimas {len(entries)} entradas ({total:.1f}h total):\n"]
    for e in entries:
        proj = e.get("project_id", ["", "—"])[1]
        task = e.get("task_id", ["", "—"])[1]
        lines.append(
            f"  [{e['id']}] {e['date']}  {e['unit_amount']:>4.1f}h  "
            f"{proj} / {task}\n"
            f"          {e['name']}"
        )
    print("\n".join(lines))


MAX_HOURS_BY_WEEKDAY = {
    0: 6.5,  # lunes
    1: 9.0,  # martes
    2: 6.5,  # miércoles
    3: 9.0,  # jueves
    4: 6.5,  # viernes
    5: 6.5,  # sábado
    6: 6.5,  # domingo
}


def _check_max_hours(date_str, hours):
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    max_h = MAX_HOURS_BY_WEEKDAY[d.weekday()]
    if hours > max_h:
        dia = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][d.weekday()]
        print(f"Error: {dia} el máximo es {max_h}h (recibido: {hours}h)", file=sys.stderr)
        sys.exit(1)


def cmd_create(args):
    if args.hours <= 0 or args.hours > 24:
        print(f"Error: las horas deben estar entre 0 y 24 (recibido: {args.hours})", file=sys.stderr)
        sys.exit(1)

    _check_max_hours(args.date, args.hours)

    client = OdooClient.get()

    record_id = client.create(
        "account.analytic.line",
        {
            "name": args.name,
            "date": args.date,
            "unit_amount": args.hours,
            "project_id": args.project,
            "task_id": args.task,
            "employee_id": EMPLOYEE_ID,
        },
        context={
            "lang": "es_ES",
            "tz": "Europe/Madrid",
            "allowed_company_ids": [1],
            "default_project_id": args.project,
        },
    )

    records = client.read(
        "account.analytic.line",
        [record_id],
        ["id", "name", "date", "unit_amount", "project_id", "task_id"],
    )
    r = records[0] if records else {}

    print(
        f"✓ Entrada creada (ID {record_id})\n"
        f"  Descripción : {r.get('name', args.name)}\n"
        f"  Fecha       : {r.get('date', args.date)}\n"
        f"  Horas       : {r.get('unit_amount', args.hours)}\n"
        f"  Proyecto    : {r.get('project_id', ['', f'ID {args.project}'])[1]}\n"
        f"  Tarea       : {r.get('task_id', ['', f'ID {args.task}'])[1]}\n"
        f"  Ver en Odoo : {BASE_URL}/web#model=account.analytic.line&id={record_id}"
    )


def cmd_search(args):
    query = args.query.lower()
    catalog_path = SCRIPT_DIR / "projects.json"
    if not catalog_path.exists():
        print("Error: no se encontró projects.json. Ejecuta 'list-projects --refresh' primero.", file=sys.stderr)
        sys.exit(1)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    matches = []
    for proj in catalog:
        if query in proj["name"].lower():
            matches.append(proj)
        else:
            for task in proj.get("tasks", []):
                if query in task["name"].lower():
                    matches.append({"id": proj["id"], "name": proj["name"], "task": task})
                    break
    if not matches:
        print("No se encontraron coincidencias.")
        return
    print(f"{len(matches)} coincidencia(s):\n")
    for m in matches:
        if "task" in m:
            print(f"  [{m['id']}] {m['name']}  →  [{m['task']['id']}] {m['task']['name']}")
        else:
            tasks = ", ".join(f"[{t['id']}] {t['name']}" for t in m.get("tasks", []))
            print(f"  [{m['id']}] {m['name']}")
            print(f"      Tareas: {tasks}")


def main():
    parser = argparse.ArgumentParser(description="Odoo Timesheet CLI")
    sub = parser.add_subparsers(dest="command")

    p_projects = sub.add_parser("list-projects", help="Listar proyectos y tareas")
    p_projects.add_argument("--refresh", action="store_true", help="Forzar actualización de caché")

    p_search = sub.add_parser("search", help="Buscar proyecto/tarea localmente en projects.json")
    p_search.add_argument("query", help="Texto a buscar")

    p_ts = sub.add_parser("list-timesheets", help="Listar entradas de horas")
    p_ts.add_argument("--from", dest="date_from", default="", help="Fecha inicio YYYY-MM-DD")
    p_ts.add_argument("--to", dest="date_to", default="", help="Fecha fin YYYY-MM-DD")
    p_ts.add_argument("--today", action="store_true", help="Solo entradas de hoy")
    p_ts.add_argument("--limit", type=int, default=20, help="Máximo de entradas")

    p_create = sub.add_parser("create", help="Crear entrada de horas")
    p_create.add_argument("--name", required=True, help="Descripción del trabajo")
    p_create.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    p_create.add_argument("--hours", type=float, required=True, help="Horas dedicadas")
    p_create.add_argument("--project", type=int, required=True, help="ID del proyecto")
    p_create.add_argument("--task", type=int, required=True, help="ID de la tarea")

    args = parser.parse_args()
    if args.command == "list-projects":
        cmd_list_projects(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "list-timesheets":
        cmd_list_timesheets(args)
    elif args.command == "create":
        cmd_create(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
