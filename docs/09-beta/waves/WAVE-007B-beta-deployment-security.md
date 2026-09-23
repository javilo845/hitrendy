# WAVE-007B — Despliegue beta, cookies, CORS y CSRF

## Objetivo

Desplegar staging/beta con frontend y backend públicos y sesión estable entre dominios.

## Contexto del repositorio


CI ya pasa. Falta runtime público.


## Alcance


- hosting;
- build/start;
- release migration;
- health;
- CORS;
- cookie;
- CSRF;
- trusted hosts;
- smoke test.


## Inspección obligatoria

Antes de editar:


- Dockerfiles;
- CI;
- main/CORS;
- identity cookie;
- frontend API URL;
- docs.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Elegir frontend según static export real.
2. Configurar Render backend.
3. Release command Alembic.
4. Añadir live/ready.
5. Configurar orígenes exactos.
6. Implementar CSRF.
7. Ajustar SameSite según dominios.
8. Probar registro/login/recarga/logout.
9. Añadir smoke posterior al deploy.


## Contratos


No usar wildcard CORS con cookies.


## Pruebas obligatorias


- navegadores;
- cookie;
- CSRF missing/valid;
- staging DB;
- health;
- smoke;
- CI.


## Criterios de aceptación


- [ ] URL pública.
- [ ] Sesión persiste.
- [ ] CSRF.
- [ ] CORS exacto.
- [ ] Migración controlada.
- [ ] Provider demo prohibido.


## Prohibiciones


- No usar Vercel Hobby para uso comercial.
- No imprimir env.
- No migrar en cada réplica.


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
