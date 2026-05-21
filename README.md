# Odoo Timesheet Bot — OpenCode Skill

Skill para [OpenCode](https://opencode.ai) que permite imputar horas en Odoo usando lenguaje natural. Diseñado para el equipo de EDF.

## Que hace

- **Imputar horas** desde lenguaje natural: *"hoy he estado 3h configurando el CI pipeline"*
- **Ver entradas**: *"¿cuántas horas llevo hoy?"*
- **Consultar proyectos**: *"¿en qué proyectos puedo imputar?"*
- **Validacion automatica** de maximo de horas por dia (L/M/V: 6.5h, M/J: 9h)

## Requisitos

- Python 3.10+
- Cuenta en Odoo (next.edf.global)

## Instalacion

### Mac / Linux

```bash
git clone https://github.com/GarriguesN/odoo-timesheet-bot.git
cd odoo-timesheet-bot
python3 install.py
```

O usando el wrapper:

```bash
./install.sh
```

### Windows

```powershell
git clone https://github.com/GarriguesN/odoo-timesheet-bot.git
cd odoo-timesheet-bot
python install.py
```

O haciendo doble clic en `install.bat`.

### Que hace el instalador

1. Crea un venv e instala `requests`
2. Copia los archivos del skill al directorio de configuracion de OpenCode
   - Mac/Linux: `~/.config/opencode/skills/odoo-timesheet/`
   - Windows: `C:\Users\<tu_usuario>\.config\opencode\skills\odoo-timesheet\`
3. Pide tus credenciales de Odoo y crea `.env`
4. Actualiza las rutas en `SKILL.md` para tu sistema
5. Verifica la conexion con Odoo

### Instalacion manual

<details>
<summary>Mac / Linux</summary>

```bash
# 1. Crear venv
python3 -m venv .venv && source .venv/bin/activate && pip install requests

# 2. Copiar skill
SKILL_DIR=~/.config/opencode/skills/odoo-timesheet
mkdir -p "$SKILL_DIR"
cp odoo_cli.py "$SKILL_DIR/"
cp skill.md "$SKILL_DIR/SKILL.md"

# 3. Configurar credenciales
cp .env.example "$SKILL_DIR/.env"
# Edita $SKILL_DIR/.env con tus credenciales de Odoo

# 4. Actualizar ruta del venv en SKILL.md
sed -i '' "s|<ruta_al_venv>|$(pwd)|" "$SKILL_DIR/SKILL.md"
```

</details>

<details>
<summary>Windows</summary>

```powershell
# 1. Crear venv
python -m venv .venv
.\.venv\Scripts\activate
pip install requests

# 2. Copiar skill
$SKILL_DIR = "$env:USERPROFILE\.config\opencode\skills\odoo-timesheet"
New-Item -ItemType Directory -Force -Path $SKILL_DIR
Copy-Item odoo_cli.py $SKILL_DIR\
Copy-Item skill.md "$SKILL_DIR\SKILL.md"

# 3. Configurar credenciales
Copy-Item .env.example "$SKILL_DIR\.env"
# Edita $SKILL_DIR\.env con tus credenciales de Odoo

# 4. Actualizar ruta del venv en SKILL.md
(Get-Content "$SKILL_DIR\SKILL.md") -replace '<ruta_al_venv>', $PWD.Path | Set-Content "$SKILL_DIR\SKILL.md"
```

</details>

## Configuracion

Edita el archivo `.env` en el directorio del skill (`~/.config/opencode/skills/odoo-timesheet/.env`):

```env
ODOO_URL=https://next.edf.global
ODOO_USER=tu_email@email.com
ODOO_PASSWORD=tu_contraseña
ODOO_EMPLOYEE_ID=35
```

> Para obtener tu `ODOO_EMPLOYEE_ID`, abre tu perfil en Odoo y mira el ID en la URL.

## Uso del CLI (independiente de OpenCode)

```bash
# Mac / Linux
PYTHON=./.venv/bin/python3
CLI=~/.config/opencode/skills/odoo-timesheet/odoo_cli.py

# Windows
PYTHON=.venv\Scripts\python.exe
CLI=%USERPROFILE%\.config\opencode\skills\odoo-timesheet\odoo_cli.py

# Listar proyectos y tareas
$PYTHON $CLI list-projects

# Buscar localmente (sin llamar a Odoo)
$PYTHON $CLI search marketing

# Ver horas de hoy
$PYTHON $CLI list-timesheets --today

# Ver horas de un rango
$PYTHON $CLI list-timesheets --from 2026-05-19 --to 2026-05-21

# Crear entrada
$PYTHON $CLI create --name "Configurando CI pipeline" --date 2026-05-21 --hours 2.5 --project 233 --task 5422
```

## Uso con OpenCode

Una vez instalado el skill, simplemente escribe en OpenCode:

| Ejemplo | Que hace |
|---|---|
| "hoy he estado 3h con el bug de la landing" | Imputa 3h en MARKETING/Landings |
| "imputar desde las 9 hasta las 11:30 configurando Odoo" | Calcula 2.5h, imputa en PROYECTOS INTERNOS/Configuracion |
| "¿cuántas horas llevo hoy?" | Lista las entradas del dia |
| "ayer 1h en reunion de marketing" | Imputa 1h en MARKETING/Reuniones, fecha de ayer |

## Maximo de horas por dia

El CLI valida automaticamente:

| Dia | Maximo |
|---|---|
| Lunes, miercoles, viernes | 6.5h |
| Martes, jueves | 9h |

Si intentas imputar mas, muestra un error y no crea la entrada.

## Estructura del repositorio

```
odoo-timesheet-bot/
├── odoo_cli.py       # CLI autocontenido (sin dependencia MCP)
├── skill.md          # Instrucciones del skill para OpenCode
├── projects.json     # Catálogo local de proyectos y tareas (búsqueda sin red)
├── install.py        # Instalador multiplataforma (Python)
├── install.sh        # Wrapper Mac/Linux
├── install.bat       # Wrapper Windows
├── .env.example      # Plantilla de credenciales
├── mcp_server.py     # Servidor MCP (alternativa, requiere `pip install mcp`)
└── README.md
```

## Como funciona

El CLI (`odoo_cli.py`) se conecta a Odoo via JSON-RPC:

1. Auto-detecta el nombre de la base de datos (via `/web/database/list` o fallback por login web)
2. Autentica con las credenciales del `.env`
3. Opera sobre `account.analytic.line` para crear/listar entradas
4. Cachea el catalogo de proyectos en `projects_cache.json` (24h TTL)

El skill (`skill.md`) le dice a OpenCode como usar el CLI: que datos extraer del mensaje del usuario, como hacer matching de proyectos/tareas, y el flujo de confirmacion antes de crear.

## Licencia

MIT
