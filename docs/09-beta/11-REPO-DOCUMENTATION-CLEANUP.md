# Plan de limpieza moderada del repositorio

## 1. Política

No borrar por impulso. Primero clasificar, luego retirar referencias, después archivar y finalmente eliminar duplicados confirmados.

## 2. Mantener como núcleo

```text
.github/
contracts/
design/
scripts/
starter/backend/
starter/web/
docker-compose.yml
.env.example
package.json
package-lock.json
Makefile
```

## 3. Actualizar

```text
README.md
AGENTS.md
CLAUDE.md
project-manifest.yaml
docs/INDEX.md
docs/00-product/
docs/02-ux/
docs/03-architecture/
docs/04-ai/
docs/05-api/
docs/06-implementation/
```

Cambios:

- beta como ruta principal;
- demo como legacy/test;
- tendencias dentro del roadmap;
- waves 001–005 marcadas como realizadas;
- waves 006+ como plan activo;
- nueva fuente de verdad.

## 4. Archivar

Destino:

```text
archive/legacy-demo/
```

Candidatos:

```text
demo/
docs/07-demo/
IMPLEMENTATION_PROMPT.md
backlogs reemplazados
prompts antiguos
```

Solo mover después de:

- revisar referencias;
- actualizar CI/scripts;
- confirmar que nadie los importa;
- conservar historial Git.

## 5. Conservar funcionalmente, pero ocultar

Provider demo:

- mantener para unit tests;
- mantener para desarrollo explícito;
- renombrar conceptualmente a `fake/test provider` en documentación;
- no ofrecer botón de demo;
- no permitir producción.

## 6. `AGENTS.md`

Debe indicar:

- `starter/` es implementación principal.
- No usar `demo/`.
- No inventar tendencias.
- Leer el plan beta.
- Ejecutar CI equivalente.
- No hacer commit/push.
- No modificar waves anteriores sin bug demostrado.
- No activar proveedores pagados.
- No exponer secretos.

## 7. `project-manifest.yaml`

Reescribir con YAML válido:

- versión;
- estado;
- entrypoints;
- runtimes;
- servicios;
- migración head;
- capacidades;
- documentos fuente;
- comandos;
- no-goals;
- completed waves;
- active wave.

Validar en CI.

## 8. Nuevo índice

Agregar:

```text
docs/09-beta/
```

Con los documentos principales de este paquete después de revisión.

## 9. No versionar

- handoff zips temporales;
- `.env`;
- `.venv`;
- `node_modules`;
- DB locales;
- uploads locales;
- resultados de agentes;
- logs;
- caches.

## 10. Entrega de limpieza futura

La limpieza debe ser una wave separada con:

- inventario;
- mapa de referencias;
- diff;
- tests;
- enlaces corregidos;
- ninguna eliminación silenciosa.
