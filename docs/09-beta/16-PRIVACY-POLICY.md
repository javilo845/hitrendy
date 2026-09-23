---
id: BETA-PRIVACY-POLICY
kind: policy
status: accepted
version: 2026-08-02
---

# Política de privacidad de la beta cerrada

**Versión:** 2026-08-02 · **Contacto:** el correo configurado en
`SUPPORT_EMAIL`.

HiTrendy ayuda a pequeños negocios a preparar contenido para redes sociales.
Esta política describe la beta cerrada; no sustituye una revisión legal local.

## Datos que procesamos

- identidad y acceso: nombre, correo normalizado, contraseña cifrada, sesiones
  y, si se habilita, identidad de Google;
- perfil del negocio: categoría, ubicación, descripción, audiencia, voz de
  marca y preferencias;
- contenido que el usuario escribe o sube, proyectos, conversaciones, feedback
  y reportes de abuso;
- seguridad y operación: request ID, estado, duración, límites, eventos de
  uso y auditorías administrativas;
- datos técnicos mínimos necesarios para rate limiting y recuperación, como un
  hash de la IP solicitante, nunca la IP en el token de recuperación.

No solicitamos contraseñas de redes sociales ni publicamos contenido
automáticamente. Las claves de proveedores permanecen en el backend y no se
exponen al navegador.

## Finalidad y proveedores

Usamos estos datos para autenticar, completar el onboarding, generar respuestas
solicitadas, guardar artefactos editables, prevenir abuso, medir costos y
atender soporte. Una solicitud de IA puede pasar por el proveedor configurado
por el operador; cada proveedor está detrás de un adaptador reemplazable. En
modo demo no se requieren credenciales externas y el correo de recuperación se
mantiene local al proceso.

La beta no usa el contenido para entrenar un modelo durante una solicitud.
Debemos documentar cualquier nuevo proveedor o transferencia antes de
activarlo en staging.

## Retención, seguridad y derechos

La retención operativa por defecto es de 365 días (`DATA_RETENTION_DAYS`),
salvo una obligación legal o una investigación de seguridad documentada. Las
cuentas pueden iniciar la eliminación desde Configuración; el acceso se revoca
de inmediato y la purga se procesa de forma asíncrona. Las auditorías de
administración se conservan para rendición de cuentas.

Aplicamos sesiones HttpOnly, CSRF, límites de cuerpo y solicitudes, separación
por workspace, tokens de recuperación de un solo uso y hashes en reposo. Estas
medidas reducen riesgo, pero la beta no promete disponibilidad continua.

Para solicitar acceso, corrección, exportación o eliminación, usar el formulario
de soporte de la aplicación o `SUPPORT_EMAIL`. No enviar secretos en el
formulario.
