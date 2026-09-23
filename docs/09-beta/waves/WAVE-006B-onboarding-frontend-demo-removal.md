# WAVE-006B — Onboarding unificado y retiro del demo público

## Objetivo

Reemplazar el flujo frontend registro→onboarding actual por el pending signup del backend y retirar el modo demo del recorrido de usuario.

## Contexto del repositorio


El frontend tiene onboarding protegido, draft local y `demo-mode.ts`. La cuenta debe finalizarse solo en la revisión.


## Alcance


- Páginas signup multi-step.
- Persistencia de draft vía API.
- Recuperación tras recarga.
- Finalización.
- Guardas.
- Retirar botón/entrada demo.
- Mantener fakes solo en tests.


## Inspección obligatoria

Antes de editar:


- `starter/web/app/`
- componentes auth/onboarding;
- `starter/web/lib/api.ts`;
- `starter/web/lib/demo-mode.ts`;
- providers/context de auth;
- middleware/guards;
- tests web.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Mapear auth state actual.
2. Crear cliente signup.
3. Mover datos de cuenta al primer paso.
4. Usar el mismo diseño de pasos existente.
5. Autosave con debounce al backend.
6. Mostrar estados guardando/guardado/error.
7. Completar con idempotency key.
8. Redirigir solo tras sesión activa.
9. Eliminar desvío demo de API runtime público.
10. Mantener helpers fake solo dentro de tests o un entrypoint explícito de desarrollo.
11. Actualizar README y user flow mínimo.


## Contratos


Estados frontend:

```text
anonymous
pending_signup
authenticated_incomplete
authenticated_complete
```

No mostrar `workspace_name`.


## Pruebas obligatorias


- recarga en cada paso;
- doble submit;
- fallo de red;
- draft expirado;
- complete;
- guardas;
- no demo bypass;
- unit tests;
- typecheck;
- lint;
- build;
- E2E backend intactos.


## Criterios de aceptación


- [ ] Signup y onboarding se sienten como un solo proceso.
- [ ] No se crea sesión normal antes de completar.
- [ ] Draft se recupera.
- [ ] No se usa localStorage como fuente de verdad.
- [ ] No existe acceso demo visible.
- [ ] Producción usa API real.
- [ ] Frontend y CI pasan.


## Prohibiciones


- No borrar DemoContentModelProvider de tests.
- No cambiar diseño completo.
- No hardcodear español; preparar claves i18n.
- No guardar password después del start.


## Entrega del agente

1. Resumen.
2. Arquitectura encontrada.
3. Archivos modificados.
4. Migraciones y datos.
5. Contratos API/UI.
6. Seguridad.
7. Pruebas con resultados exactos.
8. Hallazgos.
9. Limitaciones.
10. Checklist marcado.



No hacer commit ni push. Dejar el working tree revisable.
