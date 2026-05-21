#!/usr/bin/env python3
"""
Instalador multiplataforma del Odoo Timesheet Skill para OpenCode.

Uso:
    python3 install.py          # Mac / Linux
    python install.py           # Windows
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


def _venv_python():
    if sys.platform == "win32":
        return REPO_DIR / ".venv" / "Scripts" / "python.exe"
    return REPO_DIR / ".venv" / "bin" / "python3"


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


def step_venv(python_cmd):
    print("[1/4] Creando virtualenv...")
    venv_dir = REPO_DIR / ".venv"
    if not venv_dir.exists():
        subprocess.run([python_cmd, "-m", "venv", str(venv_dir)], check=True)
    venv_python = _venv_python()
    subprocess.run([str(venv_python), "-m", "pip", "install", "-q", "requests"], check=True)
    print(f"    ✓ venv listo en {venv_dir}")
    return venv_python


def step_copy_skill():
    skill_dir = _skill_dir()
    print(f"[2/4] Instalando skill en {skill_dir}...")
    skill_dir.mkdir(parents=True, exist_ok=True)
    for name in ("odoo_cli.py", "skill.md", "mcp_server.py"):
        src = REPO_DIR / name
        dst = skill_dir / ("SKILL.md" if name == "skill.md" else name)
        if src.exists():
            shutil.copy2(src, dst)
    print("    ✓ Archivos copiados")
    return skill_dir


def step_env(skill_dir):
    env_path = skill_dir / ".env"
    if env_path.exists():
        print("[3/4] .env ya existe — saltando")
        return

    print("[3/4] Configurando credenciales...")
    print()
    print("    Introduce tus datos de Odoo (next.edf.global):")
    user = input("    Email: ").strip()
    password = getpass.getpass("    Contraseña: ").strip()
    employee_id = input("    Employee ID (número, míralo en tu perfil de Odoo): ").strip()

    env_path.write_text(
        f"ODOO_URL=https://next.edf.global\n"
        f"ODOO_USER={user}\n"
        f"ODOO_PASSWORD={password}\n"
        f"ODOO_EMPLOYEE_ID={employee_id}\n",
        encoding="utf-8",
    )
    print(f"    ✓ .env creado")


def step_update_skill_md(skill_dir, venv_python):
    print("[4/4] Actualizando rutas en SKILL.md...")
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    content = content.replace("<ruta_al_venv>", str(REPO_DIR))

    cli_path = skill_dir / "odoo_cli.py"
    if sys.platform == "win32":
        cli_line = f"CLI={cli_path}"
    else:
        cli_line = f"CLI={cli_path}"

    old_cli_block_start = content.find("PYTHON=")
    old_cli_block_end = content.find("\n", old_cli_block_start)
    if old_cli_block_start != -1:
        first_line_end = content.find("\n", old_cli_block_start)
        second_line_start = content.find("CLI=", first_line_end)
        second_line_end = content.find("\n", second_line_start)
        content = (
            content[:old_cli_block_start]
            + f"PYTHON={venv_python}"
            + content[first_line_end:second_line_start]
            + cli_line
            + content[second_line_end:]
        )

    skill_md.write_text(content, encoding="utf-8")
    print(f"    ✓ PYTHON={venv_python}")


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
    venv_python = step_venv(python_cmd)
    skill_dir = step_copy_skill()
    step_env(skill_dir)
    step_update_skill_md(skill_dir, venv_python)
    step_verify(venv_python, skill_dir)

    print()
    print("=== Instalacion completada ===")
    print()
    print("Luego abre OpenCode y escribe: '¿cuántas horas llevo hoy?'")


if __name__ == "__main__":
    main()
