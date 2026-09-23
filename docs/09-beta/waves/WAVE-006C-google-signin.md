# WAVE-006C — Google Sign-In

## Objetivo

Añadir Google como método de entrada al pending signup y como método de login para cuentas vinculadas.

## Contexto del repositorio


La autenticación propia ya existe. Esta wave enlaza Google sin sustituir usuarios ni sesiones.


## Alcance


- OIDC Authorization Code.
- State y PKCE.
- Pending signup para nuevo usuario.
- OAuth account para usuario existente.
- Callback seguro.
- UI de botón Google.


## Inspección obligatoria

Antes de editar:


- identity routes/models;
- settings config;
- auth UI;
- tests;
- CORS/cookies.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Añadir configuración Google.
2. Crear `oauth_accounts`.
3. Implementar start/callback.
4. Validar issuer, audience, nonce/state.
5. Crear pending signup si email nuevo.
6. Iniciar sesión si identidad vinculada.
7. Definir flujo explícito para email existente no vinculado.
8. Pedir solo openid/email/profile.
9. Añadir unlink futuro solo si queda otro método de acceso.


## Contratos


```text
GET /auth/google/start
GET /auth/google/callback
```

No enviar client secret al frontend.


## Pruebas obligatorias


- state inválido;
- code replay;
- audience incorrecto;
- cuenta nueva;
- cuenta vinculada;
- email existente;
- session;
- E2E con fake OIDC;
- no llamada real en suite.


## Criterios de aceptación


- [ ] PKCE/state.
- [ ] Una identidad no se vincula a dos usuarios.
- [ ] Nuevo Google completa onboarding.
- [ ] Login existente funciona.
- [ ] Scopes mínimos.
- [ ] Tests/CI pasan.


## Prohibiciones


- No usar librería Google Sign-In deprecada.
- No pedir scopes de YouTube/Drive.
- No crear usuario activo antes de onboarding.


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
