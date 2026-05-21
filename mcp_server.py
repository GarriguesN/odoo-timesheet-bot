#!/usr/bin/env python3
"""
MCP Server — Odoo Timesheet (next.edf.global)

Expone tres herramientas al agente de opencode:
  - odoo_list_projects     → catálogo de proyectos y tareas
  - odoo_create_timesheet  → crea una entrada de horas
  - odoo_list_timesheets   → lista entradas recientes

Instalación:
    pip install mcp requests

Configuración (en ~/.config/opencode/opencode.jsonc):
    "mcp": {
      "odoo": {
        "type": "local",
        "command": ["python3", "/Users/<tu_usuario>/.config/opencode/skills/odoo-timesheet/mcp_server.py"],
        "env": {
          "ODOO_URL": "https://next.edf.global",
          "ODOO_USER": "tu@email.com",
          "ODOO_PASSWORD": "tu_contraseña",
          "ODOO_EMPLOYEE_ID": "35"
        }
      }
    }
"""

import os
import json
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL    = os.getenv("ODOO_URL",          "https://next.edf.global")
USER        = os.getenv("ODOO_USER",         "")
PASSWORD    = os.getenv("ODOO_PASSWORD",     "")
EMPLOYEE_ID = int(os.getenv("ODOO_EMPLOYEE_ID", "35"))
DB_NAME     = os.getenv("ODOO_DB",           "")
CATALOG_TTL = timedelta(hours=24)
CATALOG_PATH = Path(__file__).parent / "projects_cache.json"

mcp = FastMCP("odoo-timesheet")

# ── Odoo client ───────────────────────────────────────────────────────────────

class _OdooClient:
    _instance = None

    def __init__(self):
        self.session = requests.Session()
        self.uid: int = 0
        self._id = 0
        self._login()

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _rpc(self, endpoint: str, params: dict):
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
            raise RuntimeError("No se pudo determinar el nombre de la base de datos de Odoo. "
                               "Configura ODOO_DB o habilita /web/database/list.")
        res = self._rpc("/web/session/authenticate", {
            "db": db, "login": USER, "password": PASSWORD
        })
        self.uid = res.get("uid")
        if not self.uid:
            raise RuntimeError("Login fallido. Revisa ODOO_USER / ODOO_PASSWORD.")

    def _detect_db_via_web_login(self) -> str:
        """
        Fallback: cuando /web/database/list está deshabilitado, hace login
        por el formulario web y lee el nombre de la BD de /web/session/get_session_info.
        """
        session = requests.Session()
        # 1. Get CSRF token
        login_page = session.get(f"{BASE_URL.rstrip('/')}/web/login", timeout=30)
        login_page.raise_for_status()
        import re
        m = re.search(r'csrf_token:\s*"([^"]+)"', login_page.text)
        csrf = m.group(1) if m else ""
        # 2. Submit login form
        resp = session.post(
            f"{BASE_URL.rstrip('/')}/web/login",
            data={"csrf_token": csrf, "login": USER, "password": PASSWORD},
            timeout=30,
            allow_redirects=False,
        )
        if resp.status_code not in (302, 303):
            raise RuntimeError("Login web falló (fallback para detectar DB).")
        # 3. Get session info
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
        result = self._rpc(
            f"/web/dataset/call_kw/{model}/read",
            {"model": model, "method": "read", "args": [ids],
             "kwargs": {"fields": fields, "context": {}}},
        )
        return result


# ── Catálogo con caché ────────────────────────────────────────────────────────

def _refresh_catalog(client: _OdooClient) -> list:
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


def _get_catalog(client: _OdooClient) -> list:
    if CATALOG_PATH.exists():
        age = datetime.now() - datetime.fromtimestamp(CATALOG_PATH.stat().st_mtime)
        if age < CATALOG_TTL:
            return json.loads(CATALOG_PATH.read_text())
    return _refresh_catalog(client)


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def odoo_list_projects(refresh: bool = False) -> str:
    """
    Devuelve el catálogo completo de proyectos activos y sus tareas en Odoo.
    Usa refresh=True para forzar actualización ignorando la caché (válida 24h).
    """
    client = _OdooClient.get()
    if refresh and CATALOG_PATH.exists():
        CATALOG_PATH.unlink()
    catalog = _get_catalog(client)

    lines = [f"Proyectos activos en Odoo ({len(catalog)} proyectos):\n"]
    for proj in catalog:
        task_str = (
            ", ".join(f"[{t['id']}] {t['name']}" for t in proj["tasks"])
            if proj["tasks"] else "sin tareas"
        )
        lines.append(f"[{proj['id']}] {proj['name']}\n    Tareas: {task_str}")
    return "\n".join(lines)


@mcp.tool()
def odoo_create_timesheet(
    name: str,
    date: str,
    hours: float,
    project_id: int,
    task_id: int,
) -> str:
    """
    Crea una entrada de parte de horas en Odoo.

    Args:
        name:       Descripción del trabajo realizado.
        date:       Fecha en formato YYYY-MM-DD.
        hours:      Horas dedicadas (ej: 1.5 para 1h 30min).
        project_id: ID numérico del proyecto (obtenido de odoo_list_projects).
        task_id:    ID numérico de la tarea (obtenido de odoo_list_projects).

    Returns:
        Confirmación con el ID del registro creado y un enlace directo en Odoo.
    """
    if hours <= 0 or hours > 24:
        return f"Error: las horas deben estar entre 0 y 24 (recibido: {hours})"

    client = _OdooClient.get()

    record_id = client.create(
        "account.analytic.line",
        {
            "name":        name,
            "date":        date,
            "unit_amount": hours,
            "project_id":  project_id,
            "task_id":     task_id,
            "employee_id": EMPLOYEE_ID,
        },
        context={
            "lang": "es_ES",
            "tz":   "Europe/Madrid",
            "allowed_company_ids": [1],
            "default_project_id": project_id,
        },
    )

    records = client.read(
        "account.analytic.line",
        [record_id],
        ["id", "name", "date", "unit_amount", "project_id", "task_id"],
    )
    r = records[0] if records else {}

    return (
        f"✓ Entrada creada (ID {record_id})\n"
        f"  Descripción : {r.get('name', name)}\n"
        f"  Fecha       : {r.get('date', date)}\n"
        f"  Horas       : {r.get('unit_amount', hours)}\n"
        f"  Proyecto    : {r.get('project_id', ['', f'ID {project_id}'])[1]}\n"
        f"  Tarea       : {r.get('task_id', ['', f'ID {task_id}'])[1]}\n"
        f"  Ver en Odoo : {BASE_URL}/web#model=account.analytic.line&id={record_id}"
    )


@mcp.tool()
def odoo_list_timesheets(
    limit: int = 20,
    date_from: str = "",
    date_to: str = "",
) -> str:
    """
    Lista las entradas de partes de horas del usuario actual.

    Args:
        limit:      Número máximo de entradas a devolver (defecto: 20).
        date_from:  Filtro de fecha inicio YYYY-MM-DD (opcional).
        date_to:    Filtro de fecha fin YYYY-MM-DD (opcional).

    Returns:
        Lista de entradas ordenadas por fecha descendente con el total de horas.
    """
    client = _OdooClient.get()

    domain: list = [
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
        limit=limit,
        order="date desc",
    )

    if not entries:
        return "No se encontraron entradas con los filtros indicados."

    total = sum(e.get("unit_amount", 0) for e in entries)
    lines = [f"Últimas {len(entries)} entradas ({total:.1f}h total):\n"]
    for e in entries:
        proj = e.get("project_id", ["", "—"])[1]
        task = e.get("task_id",    ["", "—"])[1]
        lines.append(
            f"  [{e['id']}] {e['date']}  {e['unit_amount']:>4.1f}h  "
            f"{proj} / {task}\n"
            f"          {e['name']}"
        )
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
