#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$HOME/.config/opencode/skills/odoo-timesheet"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Odoo Timesheet Skill — Instalador ==="
echo ""

# 1. Venv
echo "[1/4] Creando virtualenv..."
if [ ! -d "$REPO_DIR/.venv" ]; then
    python3 -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/pip" install -q requests
echo "    ✓ venv listo en $REPO_DIR/.venv"

# 2. Copiar archivos del skill
echo "[2/4] Instalando skill en $SKILL_DIR..."
mkdir -p "$SKILL_DIR"
cp "$REPO_DIR/odoo_cli.py" "$SKILL_DIR/odoo_cli.py"
cp "$REPO_DIR/skill.md" "$SKILL_DIR/SKILL.md"
cp "$REPO_DIR/mcp_server.py" "$SKILL_DIR/mcp_server.py" 2>/dev/null || true
echo "    ✓ Archivos copiados"

# 3. .env
if [ ! -f "$SKILL_DIR/.env" ]; then
    echo "[3/4] Configurando credenciales..."
    echo ""
    echo "    Introduce tus datos de Odoo (next.edf.global):"
    read -rp "    Email: " ODOO_USER
    read -rsp "    Contraseña: " ODOO_PASSWORD; echo ""
    read -rp "    Employee ID (numero, miralo en tu perfil de Odoo): " ODOO_EMPLOYEE_ID

    cat > "$SKILL_DIR/.env" <<EOF
ODOO_URL=https://next.edf.global
ODOO_USER=$ODOO_USER
ODOO_PASSWORD=$ODOO_PASSWORD
ODOO_EMPLOYEE_ID=$ODOO_EMPLOYEE_ID
EOF
    echo "    ✓ .env creado en $SKILL_DIR/.env"
else
    echo "[3/4] .env ya existe en $SKILL_DIR/.env — saltando"
fi

# 4. Actualizar ruta del venv en SKILL.md
echo "[4/4] Actualizando rutas en SKILL.md..."
VENV_PYTHON="$REPO_DIR/.venv/bin/python3"
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|<ruta_al_venv>|$REPO_DIR|" "$SKILL_DIR/SKILL.md"
else
    sed -i "s|<ruta_al_venv>|$REPO_DIR|" "$SKILL_DIR/SKILL.md"
fi
echo "    ✓ PYTHON=$VENV_PYTHON"

echo ""
echo "=== Instalacion completada ==="
echo ""
echo "Verifica que funciona:"
echo "    $VENV_PYTHON $SKILL_DIR/odoo_cli.py list-projects"
echo ""
echo "Luego abre OpenCode y escribe: '¿cuántas horas llevo hoy?'"
