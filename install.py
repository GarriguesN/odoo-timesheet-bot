#!/usr/bin/env python3
"""
Instalador multiplataforma del Odoo Timesheet Skill para OpenCode.

Uso:
    python3 install.py          # Mac / Linux
    python install.py           # Windows

Instala TODO en ~/.config/opencode/skills/odoo-timesheet/ (incluido el venv).
Puedes borrar el repo clonado tras la instalacion.
"""

import os
import sys
import shutil
import subprocess
import getpass
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent


def _skill_dir():
    return Path.home() / ".config" / "opencode" / "skills" / "odoo-timesheet"


def _find_python():
    for cmd in (sys.executable, "python3", "python"):
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "Python 3" in r.stdout:
                return cmd
        except Exception:
            continue
    print("Error: no se encontró Python 3. Instálalo desde https://python.org", file=sys.stderr)
    sys.exit(1)


def _detect_db(user, password, venv_python):
    """Intenta detectar el nombre de la BD de Odoo y devolverlo como string."""
    script = (
        "import os,sys,re,requests\n"
        "url='https://next.edf.global'\n"
        "user=os.environ['U']\n"
        "pw=os.environ['P']\n"
        # Intento 1: /web/database/list
        "try:\n"
        "    r=requests.post(url+'/web/database/list',json={'jsonrpc':'2.0','method':'call','id':1,'params':{}},headers={'Content-Type':'application/json'},timeout=10)\n"
        "    dbs=r.json().get('result',[])\n"
        "    if isinstance(dbs,list) and dbs: print(dbs[0]);sys.exit(0)\n"
        "except Exception: pass\n"
        # Intento 2: web login + session info
        "try:\n"
        "    s=requests.Session()\n"
        "    page=s.get(url+'/web/login',timeout=10)\n"
        "    m=re.search(r'csrf_token:\\s*\"([^\"]+)\"',page.text)\n"
        "    csrf=m.group(1) if m else ''\n"
        "    s.post(url+'/web/login',data={'csrf_token':csrf,'login':user,'password':pw},timeout=10,allow_redirects=False)\n"
        "    info=s.post(url+'/web/session/get_session_info',json={'jsonrpc':'2.0','method':'call','id':2,'params':{}},headers={'Content-Type':'application/json'},timeout=10)\n"
        "    db=info.json().get('result',{}).get('db','')\n"
        "    if db: print(db);sys.exit(0)\n"
        "except Exception: pass\n"
        "sys.exit(1)\n"
    )
    try:
        r = subprocess.run(
            [str(venv_python), "-c", script],
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "U": user, "P": password},
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def step_venv(skill_dir, python_cmd):
    print("[1/5] Creando virtualenv...")
    venv_dir = skill_dir / ".venv"
    if not venv_dir.exists():
        subprocess.run([python_cmd, "-m", "venv", str(venv_dir)], check=True)
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python3"
    subprocess.run([str(venv_python), "-m", "pip", "install", "-q", "requests"], check=True)
    print(f"    ✓ venv listo en {venv_dir}")
    return venv_python


def step_copy_skill(skill_dir):
    print(f"[2/5] Copiando archivos del skill en {skill_dir}...")
    skill_dir.mkdir(parents=True, exist_ok=True)
    for name in ("odoo_cli.py", "skill.md", "mcp_server.py"):
        src = REPO_DIR / name
        dst = skill_dir / ("SKILL.md" if name == "skill.md" else name)
        if src.exists():
            shutil.copy2(src, dst)
    print("    ✓ Archivos copiados")


def step_env(skill_dir, venv_python):
    env_path = skill_dir / ".env"
    if env_path.exists():
        print("[3/5] .env ya existe — saltando")
        return

    print("[3/5] Configurando credenciales...")
    print()
    print("    Introduce tus datos de Odoo (next.edf.global):")
    user = input("    Email: ").strip()
    password = getpass.getpass("    Contraseña: ").strip()
    employee_id = input("    Employee ID (número, míralo en tu perfil de Odoo): ").strip()

    print("    Detectando base de datos de Odoo...", end=" ", flush=True)
    db = _detect_db(user, password, venv_python)
    if db:
        print(f"✓ ({db})")
    else:
        print("no detectada (se intentará en el primer uso)")

    lines = [
        "ODOO_URL=https://next.edf.global\n",
        f"ODOO_DB={db}\n" if db else "",
        f"ODOO_USER={user}\n",
        f"ODOO_PASSWORD={password}\n",
        f"ODOO_EMPLOYEE_ID={employee_id}\n",
    ]
    env_path.write_text("".join(lines), encoding="utf-8")
    print("    ✓ .env creado")


def step_download_catalog(venv_python, skill_dir):
    print("[4/5] Descargando catálogo de proyectos desde Odoo...")
    cli_path = skill_dir / "odoo_cli.py"
    try:
        r = subprocess.run(
            [str(venv_python), str(cli_path), "list-projects", "--refresh"],
            capture_output=True, text=True, timeout=60, errors="replace",
        )
        if r.returncode == 0:
            print("    ✓ Catálogo descargado (projects_cache.json)")
        else:
            print(f"    ⚠ No se pudo descargar el catálogo: {r.stderr.strip() or 'código ' + str(r.returncode)}")
            print("    Revisa las credenciales en", skill_dir / ".env")
    except Exception as e:
        print(f"    ⚠ Error al descargar: {e}")


def step_update_skill_md(skill_dir, venv_python):
    print("[5/5] Actualizando rutas en SKILL.md...")
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    content = content.replace("<ruta_al_venv>", str(skill_dir))

    cli_path = skill_dir / "odoo_cli.py"

    old_cli_block_start = content.find("PYTHON=")
    if old_cli_block_start != -1:
        first_line_end = content.find("\n", old_cli_block_start)
        second_line_start = content.find("CLI=", first_line_end)
        second_line_end = content.find("\n", second_line_start)
        content = (
            content[:old_cli_block_start]
            + f"PYTHON={venv_python}"
            + content[first_line_end:second_line_start]
            + f"CLI={cli_path}"
            + content[second_line_end:]
        )

    skill_md.write_text(content, encoding="utf-8")
    print(f"    ✓ PYTHON={venv_python}")
    print(f"    ✓ CLI={cli_path}")


def step_verify(venv_python, skill_dir):
    print()
    print("Verificando conexion con Odoo...")
    cli_path = skill_dir / "odoo_cli.py"
    try:
        r = subprocess.run(
            [str(venv_python), str(cli_path), "list-projects"],
            capture_output=True, text=True, timeout=30, errors="replace",
        )
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            print(f"    ✓ Conexion OK — {lines[0] if lines else 'sin proyectos'}")
        else:
            print(f"    ⚠ Error de conexion: {r.stderr.strip() or 'codigo ' + str(r.returncode)}")
            print("    Revisa las credenciales en", skill_dir / ".env")
    except Exception as e:
        print(f"    ⚠ No se pudo verificar: {e}")


def main():
    print("=== Odoo Timesheet Skill — Instalador ===")
    print(f"    Plataforma: {sys.platform}")
    print()

    python_cmd = _find_python()
    skill_dir = _skill_dir()
    venv_python = step_venv(skill_dir, python_cmd)
    step_copy_skill(skill_dir)
    step_env(skill_dir, venv_python)
    step_download_catalog(venv_python, skill_dir)
    step_update_skill_md(skill_dir, venv_python)
    step_verify(venv_python, skill_dir)

    print()
    print("=== Instalacion completada ===")
    print()
    print(f"Todo esta en: {skill_dir}")
    print("Puedes borrar el repo clonado si quieres.")
    print()
    print("Luego abre OpenCode y escribe: '¿cuántas horas llevo hoy?'")


if __name__ == "__main__":
    main()
