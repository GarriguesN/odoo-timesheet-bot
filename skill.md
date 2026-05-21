---
name: odoo-timesheet
description: "Gestión de partes de horas en Odoo (next.edf.global) mediante lenguaje natural. Permite imputar horas, listar entradas y consultar proyectos/tareas. Acciones: imputar, listar horas, listar proyectos, crear entrada. Triggers: 'hoy he estado', 'imputar horas', 'parte de horas', 'cuántas horas', 'registrar tiempo'."
---

# Odoo Timesheet — Guía de uso

Skill para interactuar con el sistema de partes de horas de Odoo en next.edf.global.
Usa el CLI `odoo_cli.py` para todas las operaciones.

## Variables del CLI

```
PYTHON=<ruta_al_venv>/.venv/bin/python3
CLI=<skill_dir>/odoo_cli.py
```

> Estas variables se configuran automáticamente al ejecutar `install.py` (o `install.sh` / `install.bat`).
> En Windows, PYTHON apunta a `.venv\Scripts\python.exe` y CLI a `%APPDATA%\opencode\skills\odoo-timesheet\odoo_cli.py`.

## Cuándo activar este skill

Actívalo cuando el usuario:
- Describa trabajo realizado con mención de tiempo ("hoy he estado X horas...", "esta mañana dediqué...")
- Pida imputar, registrar o crear una parte de horas
- Quiera ver sus entradas recientes o del día/semana
- Pregunte por proyectos o tareas disponibles

## Flujo: imputar horas desde lenguaje natural

### Paso 0 — Fecha actual (CRÍTICO)

- La fecha de HOY se toma siempre del contexto del sistema (`currentDate`), NUNCA de las entradas previas de Odoo.
- Si el usuario dice "ayer", resta 1 día a hoy. Si dice "el lunes", calcula la fecha.
- Si no menciona fecha → hoy.
- Las entradas que ya existen en Odoo de días anteriores NO afectan la fecha de la nueva imputación.

### Paso 1 — Extraer datos del mensaje

| Campo | Cómo extraerlo |
|---|---|
| `hours` | "3 horas" → 3.0 · "hora y media" → 1.5 · "45 minutos" → 0.75 · "2h30" → 2.5 · **Rango: "desde las 9 hasta las 11:30" → 2.5h** (calcula Y - X en horas decimales, no preguntes) |
| `date` | Sin mención → hoy · "ayer" → hoy-1 · fecha explícita → usar tal cual |
| `project_id` | Matching semántico flexible contra el nombre del proyecto (ver atajos abajo) |
| `task_id` | Matching semántico flexible contra el nombre de la tarea (ver atajos abajo) |
| `name` | Descripción corta y profesional del trabajo, en español |

**Máximo de horas por día** (verificación automática del CLI, pero avisa al usuario antes de intentar crear):
- Lunes, miércoles, viernes → máx 6.5h
- Martes, jueves → máx 9h

Si las horas calculadas superan el máximo del día, avisa al usuario y sugiere ajustar antes de ejecutar el `create`.

**Rangos de hora**: Si el usuario dice "desde las X hasta las Y", calcula la duración como (Y - X) en horas decimales. Muestra el cálculo en la confirmación. No preguntes si redondear.

**Entradas existentes**: El usuario solo pide CREAR una nueva entrada. No preguntes si quiere reemplazar o modificar las anteriores.

### Paso 2 — Matching de proyecto y tarea (orden de prioridad)

**1. Atajos frecuentes** (úsalo directamente sin llamar a nada):
- `[233] 2026-PROYECTOS INTERNOS` → internal, herramientas, Odoo, bugfix, investigación, configuración, CI/CD, deploy, infra
  - `[7263] Bugfixing` → arreglo de bugs
  - `[5425] Investigación` → exploración, spike, R&D
  - `[5422] Configuracion` → setup, configuración de herramientas
  - `[6221] Imputaciones` → partes de horas, registros de tiempo
  - `[5349] Configuración Odoo` → config Odoo
  - `[6386] Infraestructura` → servidores, infra
- `[152] 2025-MARKETING` → landing, marketing, contenido, deploy, web
  - `[6404] Landings` → páginas de aterrizaje, HTML/CSS/JS
  - `[1576] Producto` → producto, features

**2. Búsqueda local (SIN llamar a Odoo)** — si no hay atajo directo, busca en el catálogo local `projects.json`:
```
$PYTHON $CLI search <keyword>
```
Ejemplo: si el usuario dice "arreglando un bug en la landing", busca: `$PYTHON $CLI search landing`

**3. Sincronización con Odoo** — solo si `search` no devuelve resultados o el usuario pide ver todos los proyectos:
```
$PYTHON $CLI list-projects --refresh
```

### Paso 3 — Mostrar confirmación antes de crear

**SIEMPRE** muestra un resumen antes de crear:

```
┌─ Parte de horas ────────────────────────────────────────────────
│  Descripción : <name>
│  Fecha       : <date>
│  Horas       : <hours>
│  Proyecto    : [<id>] <nombre>
│  Tarea       : [<id>] <nombre>
└─────────────────────────────────────────────────────────────────
¿Crear? [S/n]
```

Solo crea la entrada tras confirmación explícita del usuario ("s", "sí", "dale", "ok", "créalo", "venga").

### Paso 4 — Crear la entrada

Ejecuta:
```
$PYTHON $CLI create --name "<name>" --date <YYYY-MM-DD> --hours <float> --project <id> --task <id>
```

### Paso 5 — Confirmar creación

El CLI ya muestra:
```
✓ Entrada creada (ID <id>)
  Ver en Odoo: https://next.edf.global/web#model=account.analytic.line&id=<id>
```

## Comandos del CLI

| Acción | Comando |
|---|---|
| Buscar localmente | `$PYTHON $CLI search <keyword>` (sin red, instantáneo) |
| Obtener catálogo | `$PYTHON $CLI list-projects` |
| Forzar refresco | `$PYTHON $CLI list-projects --refresh` |
| Ver horas de hoy | `$PYTHON $CLI list-timesheets --today` |
| Ver horas de un rango | `$PYTHON $CLI list-timesheets --from 2026-05-19 --to 2026-05-21` |
| Crear entrada | `$PYTHON $CLI create --name "..." --date 2026-05-21 --hours 3.5 --project 152 --task 6404` |

## Ejemplos de uso

**Imputar horas:**
> "hay que imputar desde las 9 hasta ahora (11:30) configurando el CI pipeline"
→ Fecha: hoy · Horas: 2.5 · Proyecto: [233] PROYECTOS INTERNOS · Tarea: [5422] Configuracion

> "Hoy he estado 3h arreglando el admin page de Flashcards"
→ Fecha: hoy · Horas: 3.0 · Proyecto: [222] Flashcards RoadMap · Tarea: [5049] Admin Refactor

> "Ayer, hora y media investigando RAG"
→ Fecha: ayer · Horas: 1.5 · Proyecto: [233] PROYECTOS INTERNOS · Tarea: [5425] Investigación

**Ver entradas:**
> "¿Cuántas horas llevo hoy?" → `$PYTHON $CLI list-timesheets --today`
> "Muéstrame mis partes de esta semana" → `$PYTHON $CLI list-timesheets --from <lunes> --to <hoy>`

**Listar proyectos:**
> "¿En qué proyectos puedo imputar?" → `$PYTHON $CLI list-projects`
