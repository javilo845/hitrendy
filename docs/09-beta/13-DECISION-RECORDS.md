# Decisiones de arquitectura propuestas

## ADR-BETA-001 — PostgreSQL permanece como base principal

**Estado:** propuesto para aceptar.  
**Decisión:** usar PostgreSQL administrado; Supabase es candidato de hosting, no un cambio de modelo de datos.  
**Razón:** SQLAlchemy, Alembic, relaciones y E2E ya existen.  
**Consecuencia:** no usar Firebase como reemplazo.

## ADR-BETA-002 — Autenticación propia + Google

**Decisión:** conservar usuarios/sesiones del backend y añadir OAuth account linking.  
**Razón:** evitar migrar simultáneamente identidad y persistencia.  
**Consecuencia:** no adoptar Supabase Auth en la primera beta.

## ADR-BETA-003 — Cuenta finalizada al completar onboarding

**Decisión:** pending signup temporal, finalización atómica.  
**Razón:** decisión de producto confirmada.  
**Consecuencia:** nueva tabla y endpoints.

## ADR-BETA-004 — Un negocio visible por cuenta

**Decisión:** conservar workspace internamente; imponer un negocio activo.  
**Razón:** UX simple sin destruir extensibilidad.

## ADR-BETA-005 — Capability router

**Decisión:** seleccionar modelo por capacidad y nivel.  
**Razón:** múltiples modelos, cuotas y proveedores.  
**Consecuencia:** deprecar gradualmente el único `AI_MODEL`.

## ADR-BETA-006 — Free no significa disponible

**Decisión:** estado dinámico y degradación.  
**Razón:** cuotas, saturación, restricciones y términos.  
**Consecuencia:** endpoint de capacidades.

## ADR-BETA-007 — Tendencias requieren evidencia

**Decisión:** una tendencia debe guardar fuente, URL, fecha y región.  
**Razón:** evitar alucinaciones.

## ADR-BETA-008 — Uso como ledger

**Decisión:** eventos inmutables y ajustes auditados.  
**Razón:** costos y demo.

## ADR-BETA-009 — Sin comando secreto

**Decisión:** reset de uso por CLI/admin autenticado.  
**Razón:** una puerta trasera oculta es insegura.

## ADR-BETA-010 — Beta textual antes de multimedia

**Decisión:** cerrar cuenta, nube y texto antes de imagen/video.  
**Razón:** alcanza la promesa inicial con menor riesgo y costo.
