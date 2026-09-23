---
id: ADR-005
kind: architecture_decision
status: accepted
related: [ARCH-SEC-001, ADR-004]
---

# ADR-005: Conexiones sociales propias sin publicación

## Contexto

HiTrendy necesita conectar cuentas que el usuario ya posee para habilitar
capacidades futuras de métricas propias. Los tokens OAuth son credenciales de
portador y los proveedores no comparten permisos, soporte de PKCE ni términos.

## Decisión

- El dominio usa un puerto `SocialConnectionProvider`; cada red se implementa
  detrás de ese contrato y nunca filtra objetos del proveedor al dominio o a la
  interfaz.
- Los tokens se almacenan únicamente como sobres AES-256-GCM, ligados por datos
  asociados al workspace, proveedor y propósito (`access_token` o
  `refresh_token`). El estado OAuth y el verificador PKCE viven solo en el
  almacenamiento efímero y son de un solo uso.
- Cada proveedor declara scopes mínimos y disponibilidad explícita. Instagram
  solo conecta cuentas profesionales; TikTok y X permanecen deshabilitados
  hasta cumplir sus requisitos de aprobación o facturación.
- Esta wave no publica, programa, raspa timelines ni importa publicaciones.
  La desconexión elimina siempre los tokens locales y solo afirma revocación
  remota cuando el proveedor la confirma.

## Consecuencias

- Se puede ejecutar y probar todo el flujo con el proveedor demo offline.
- Añadir una red requiere un adaptador, configuración validada y pruebas de
  scopes, aislamiento, revocación y errores; no requiere cambiar el modelo de
  identidad.
- La renovación automática y las métricas propias necesitan decisiones y
  contratos específicos por plataforma antes de habilitarse.
