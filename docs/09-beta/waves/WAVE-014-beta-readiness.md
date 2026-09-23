# WAVE-014 — Preparación de beta cerrada

## Objetivo

Convertir staging funcional en una beta operable con monitoreo, backups, privacidad y soporte.

## Contexto del repositorio


Todas las capacidades esenciales ya deben existir.


## Alcance


- monitoring;
- error tracking;
- backups/restore;
- reset password;
- email;
- abuse;
- feedback;
- privacy/terms;
- runbook.


## Inspección obligatoria

Antes de editar:


- all services;
- CI/deploy;
- docs;
- admin.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Threat review.
2. backups and restore drill.
3. alerting.
4. password reset.
5. email verification decision.
6. cost alarms.
7. beta invite list.
8. feedback.
9. incident runbook.
10. browser/mobile acceptance.


## Contratos


SLOs modestos y explícitos; no afirmar SLA de servicios free.


## Pruebas obligatorias


- restore;
- reset password;
- abuse;
- account deletion;
- smoke;
- load small;
- real user checklist.


## Criterios de aceptación


- [ ] Restore probado.
- [ ] Alertas.
- [ ] Cost cap.
- [ ] Privacy.
- [ ] Support path.
- [ ] Beta test.


## Prohibiciones


- No lanzar públicamente sin políticas.
- No afirmar alta disponibilidad con tiers free.


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

## Estado de implementación — 2026-08-02

La wave quedó implementada como una beta cerrada operable, con límites
explícitos:

- monitoreo HTTP local, endpoint Prometheus, request IDs y error tracker por
  interfaz; la entrega de alertas externas sigue siendo responsabilidad del
  despliegue;
- backup SQLite/PostgreSQL, manifiesto SHA-256 y restore drill seguro;
- recuperación de contraseña de un solo uso con adaptadores demo/Resend;
- decisión de verificación de correo `disabled` para beta cero-costo; Google
  sólo se habilita cuando el operador configura OAuth, y no se presenta como
  integración disponible por defecto;
- invitaciones de beta con hash, expiración, asociación opcional a correo,
  revocación y CLI auditada;
- feedback, reportes de abuso, páginas versionadas de privacidad/términos y
  ruta de soporte;
- presupuesto mensual en modo `soft` o `hard`, compensación administrativa
  auditada y pruebas de frontend desktop/móvil.

### Checklist de entrega

- [x] Restore automatizado y drill documentado.
- [x] Alertas de error/costo representadas en métricas y configuración.
- [x] Cost cap antes de generación en `hard`.
- [x] Privacy y terms versionados y enlazados desde la UI.
- [x] Support path de feedback y abuso.
- [x] Beta test: smoke, carga pequeña, Playwright desktop/móvil y checklist de
  tester real.
- [x] Threat review documentado con riesgos aceptados y decisión de apertura.
- [ ] Restauración de PostgreSQL de staging ejecutada por el operador: requiere
  acceso a la base y queda como gate antes de invitar testers externos.
