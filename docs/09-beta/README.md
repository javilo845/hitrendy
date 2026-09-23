# HiTrendy Beta Architecture v1

**Fecha:** 2026-07-26  
**Repositorio auditado:** https://github.com/Starryboyjosh/Trend-AI  
**Objetivo de producto:** una persona crea su cuenta y, en menos de cinco minutos, obtiene un post de Instagram adecuado para su negocio.

Este paquete reemplaza el enfoque de “demo como producto principal” por un plan de beta real, sin borrar todavía el provider falso ni las pruebas que dependen de él.

## Cómo usar este paquete

1. Leer `00-MASTER-PLAN.md`.
2. Revisar `01-CURRENT-STATE-AUDIT.md` para entender qué ya existe.
3. Adoptar las decisiones de `02-BETA-PRODUCT-CONTRACT.md`.
4. Consultar `03-FREE-PAID-API-MATRIX.md` antes de registrar o pagar servicios.
5. Implementar las waves en orden, empezando por `waves/WAVE-006A-pending-signup-backend.md`.
6. Entregar cada wave como un commit independiente después de validar su checklist.
7. No iniciar tendencias, imágenes o video antes de cerrar la beta textual.

## Principios no negociables

- Un negocio por cuenta durante la beta.
- Onboarding obligatorio.
- La cuenta se finaliza al confirmar todo el onboarding.
- Correo/contraseña y Google.
- Interfaz en español, inglés y portugués.
- Idioma del contenido configurable por negocio.
- El usuario ve niveles `rápido`, `equilibrado` y `calidad`, no nombres técnicos.
- Las recomendaciones tienen prioridad sobre texto, imágenes y video.
- La aplicación nunca inventa tendencias ni aparenta usar una API que no está disponible.
- No se añaden puertas traseras. Los reinicios de uso se hacen mediante una CLI o panel administrativo protegido y auditado.
- La base principal sigue siendo PostgreSQL.
- El frontend nunca recibe claves privadas de proveedores.
- Los servicios gratuitos se tratan como recursos limitados y degradables, no como disponibilidad garantizada.
- Cada implementación debe preservar las pruebas y CI existentes.

## Estructura

- `00-MASTER-PLAN.md`: plan general y orden de ejecución.
- `01-CURRENT-STATE-AUDIT.md`: estado real del repositorio.
- `02-BETA-PRODUCT-CONTRACT.md`: comportamiento esperado de la beta.
- `03-FREE-PAID-API-MATRIX.md`: servicios, cuotas y restricciones.
- `04-TARGET-ARCHITECTURE.md`: arquitectura técnica objetivo.
- `05-DATA-MODEL-AND-MIGRATIONS.md`: cambios propuestos de base de datos.
- `06-AUTH-ONBOARDING-SETTINGS.md`: registro, onboarding y configuración.
- `07-AI-CAPABILITY-ROUTER.md`: enrutamiento de modelos y conciencia de disponibilidad.
- `08-TRENDS-ENGINE.md`: motor verificable de tendencias.
- `09-USAGE-COST-AND-ADMIN.md`: consumo, límites y herramientas administrativas.
- `10-DEPLOYMENT-ENVIRONMENTS.md`: entornos gratuitos y pagados.
- `11-REPO-DOCUMENTATION-CLEANUP.md`: limpieza moderada del repositorio.
- `12-AGENT-IMPLEMENTATION-STANDARD.md`: reglas para modelos de programación.
- `13-DECISION-RECORDS.md`: decisiones de arquitectura propuestas.
- `14-SOURCE-REGISTER.md`: fuentes oficiales revisadas.
- `waves/`: prompts atómicos y ejecutables.

## Primera meta liberable

La primera beta se considera funcional únicamente cuando una persona externa puede:

1. Abrir la URL pública.
2. Completar el registro y onboarding.
3. Iniciar sesión.
4. Pedir una recomendación o un post para Instagram.
5. Recibir una respuesta de un modelo real.
6. Guardar y recuperar esa respuesta.
7. Cerrar sesión y volver a encontrar sus datos.
