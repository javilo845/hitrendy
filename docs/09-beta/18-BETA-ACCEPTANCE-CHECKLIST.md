---
id: BETA-ACCEPTANCE-CHECKLIST
kind: checklist
status: active
---

# Checklist de aceptación de beta

Registrar fecha, entorno, versión, navegador, tester y resultado. Un fallo en
privacidad, aislamiento, recuperación, backup o costo bloquea la sesión.

## Preflight operativo

- [ ] `alembic upgrade head` terminó en revisión `025`.
- [ ] Se verificó un backup y su manifiesto SHA-256.
- [ ] Se ejecutó un restore drill sobre un destino aislado.
- [ ] `python scripts/beta_readiness_check.py` pasó live, ready, policies y
  metrics.
- [ ] `python scripts/load_smoke.py --requests 20 --concurrency 4` pasó sin
  generar contenido ni llamar proveedores de IA.
- [ ] `BETA_INVITES_ENABLED`, proveedor de correo, presupuesto y allowlist de
  administración coinciden con el plan de la sesión.

## Navegador y móvil

```bash
npm ci
npx playwright install --with-deps chromium
npm run web:test:e2e:beta
```

El smoke de Wave 14 ejecuta `chromium-desktop` y `chromium-mobile` (Pixel 7)
para políticas, recuperación, invitaciones y soporte. La suite completa
existente se puede ejecutar con `npm run web:test:e2e`. Confirmar además
manualmente en una ventana estrecha:

- [ ] Login, registro con código de invitación y logout.
- [ ] Onboarding completo y recarga sin perder el borrador.
- [ ] Generación demo, edición y guardado del artefacto.
- [ ] Recuperación de contraseña: correo genérico, enlace expirado y enlace de
  un solo uso.
- [ ] Settings: uso, privacidad, términos, eliminación y feedback.
- [ ] Teclado, foco visible, labels, contraste y mensajes de error/éxito.

## Tester real

1. Entregar una invitación individual a un correo controlado.
2. Crear el negocio y terminar el primer artefacto editable.
3. Abrir una segunda sesión, revisar el historial y enviar feedback.
4. Intentar una acción no autorizada y confirmar que no cruza workspace.
5. Reportar un ejemplo de abuso sin incluir secretos.
6. Solicitar eliminación y confirmar revocación de sesión.

- [ ] El tester pudo completar el flujo sin intervención técnica.
- [ ] Cada incidente tiene request ID y respuesta de soporte.
- [ ] El operador revisó alertas de error y costo durante la sesión.
