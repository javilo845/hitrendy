# Estándar de implementación para modelos de código

Este documento está escrito para que modelos menos capaces produzcan cambios revisables.

## 1. Antes de editar

El agente debe:

1. Leer el prompt completo.
2. Ejecutar `git status --short`.
3. Identificar cambios no relacionados.
4. Inspeccionar archivos reales.
5. Localizar tests existentes.
6. Confirmar migración head.
7. Resumir plan en máximo diez pasos.
8. No editar hasta completar inspección.

## 2. Regla de alcance

- Una subwave por ejecución.
- No refactors estéticos fuera del objetivo.
- No cambiar contratos sin pruebas.
- No añadir nueva librería si la existente resuelve el problema.
- No modificar migraciones históricas.
- No usar `git add .`.
- No commit.
- No push.
- No tocar handoffs.

## 3. Código

- Tipos explícitos.
- Errores normalizados.
- Dependencias inyectables.
- Secretos solo por configuración.
- Operaciones externas con timeout.
- Idempotencia en acciones mutables importantes.
- Transacciones para operaciones atómicas.
- Sin rutas absolutas.
- Sin placeholders presentados como funciones.
- Sin fallbacks pagados implícitos.

## 4. Base de datos

- Nueva migración.
- Constraints e índices.
- PostgreSQL real.
- Upgrade desde vacío.
- Upgrade desde head anterior.
- Upgrade repetido.
- Tests de concurrencia cuando aplique.
- No borrar datos sin migración de datos.

## 5. API

Cada endpoint debe definir:

- auth;
- request;
- response;
- errores;
- idempotencia;
- rate limit;
- side effects;
- auditoría.

## 6. Frontend

- Estados loading/error/empty/success.
- Doble envío protegido.
- Accesibilidad.
- Responsive.
- Textos traducibles.
- No almacenar secretos.
- No usar `localStorage` como fuente de verdad de datos críticos.
- Mostrar capability status.

## 7. Proveedores

- Adapter.
- Fake.
- health.
- timeouts.
- error mapping.
- usage.
- cost.
- no external call in normal tests.

## 8. Pruebas obligatorias

Backend:

```bash
python -m ruff check .
python -m pytest -m "not e2e"
TEST_DATABASE_URL=... python -m pytest -m e2e
```

Frontend:

```bash
npm test
npm run typecheck
npm run lint
npm run build
```

Ejecutar scripts reales del repo si difieren.

## 9. Entrega

Formato:

### Resumen
### Análisis previo
### Archivos modificados
### Migraciones
### Contratos
### Seguridad
### Pruebas y resultados
### Hallazgos
### Limitaciones
### Checklist

No declarar completo con pruebas esenciales omitidas.

## 10. Prohibiciones

- Credenciales reales.
- scraping no autorizado;
- fake trends;
- puertas traseras;
- `continue-on-error` en CI esencial;
- `|| true`;
- desactivar tests;
- cambiar a Firebase;
- duplicar sistemas de autenticación;
- introducir Supabase Auth sin ADR;
- poner OpenRouter key en Next.js.
