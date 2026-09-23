# WAVE-010A — Framework de fuentes de tendencias

## Objetivo

Crear contratos, persistencia, scoring y reglas de evidencia sin conectar todavía todas las APIs.

## Contexto del repositorio


La documentación antigua relegaba tendencias. La nueva beta las necesita, pero no deben bloquear el post textual.


## Alcance


- interfaces;
- models;
- migrations;
- fake sources;
- pipeline;
- scoring;
- capability integration.


## Inspección obligatoria

Antes de editar:


- nuevo dominio trends;
- scheduler/jobs existentes;
- business;
- capabilities;
- tests.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. TrendSource.
2. Evidence.
3. Runs/items/scores.
4. Fake adapters.
5. Deterministic grouping.
6. Scoring versionado.
7. no-evidence rule.
8. API list/detail/refresh.


## Contratos


Cada tendencia requiere source URL, observed_at y region.


## Pruebas obligatorias


- no evidence;
- dedupe;
- scoring;
- partial sources;
- idempotent run;
- workspace relevance;
- E2E.


## Criterios de aceptación


- [ ] No fake trends.
- [ ] Evidencia persistida.
- [ ] Scoring reproducible.
- [ ] Sources degradables.


## Prohibiciones


- No scraping.
- No LLM como fuente.
- No TikTok/Instagram/X fake.


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

## Reglas operativas del framework

WAVE-010A acepta únicamente evidencia verificable (`source`, URL http/https,
`observed_at` y región). Un candidato que no la tenga se descarta antes de
persistir o de aparecer en list/detail. Los adapters demo son deterministas y
no representan una red social ni consultan servicios externos.

La deduplicación usa URL canónica por fuente, región y ventana de observación;
la agrupación usa título normalizado exacto, región, categoría y una ventana UTC
semanal ISO versionada (`utc-week-v1`), calculada a partir de la fecha UTC, no
desde la hora local del servidor: el mismo dato siempre obtiene el mismo bucket.
Esto agrupa el mismo tema atribuido por varias fuentes durante una semana, pero
permite que vuelva a aparecer como una tendencia nueva en una semana posterior.
La misma URL puede reobservarse en una ventana posterior y queda auditada como
una nueva observación. Las fuentes se ordenan por identificador antes de
procesarse, por lo que el resultado no depende del orden de llegada. El
`observed_at` del item es la observación válida más reciente de su grupo y el
scoring `trend-v1` se recalcula con ella. La relevancia de workspace se guarda
por separado y nunca duplica la evidencia global.

Dentro de la misma ventana, una URL canónica existente se reutiliza y se
actualiza sólo si la nueva observación es más reciente; su confianza conserva
el máximo determinista entre ambas observaciones. Cada run queda vinculado a
esa observación mediante `trend_run_evidence`.

La observación es global y se vincula a los items mediante una asociación
idempotente; por ello una misma URL verificable puede atribuirse a títulos
distintos sin colisionar. Antes de asociarla, región solicitada, región de
candidato y región de evidencia se normalizan a mayúsculas y deben coincidir.
La ventana UTC de evidencia debe coincidir con la del candidato. Una evidencia
incoherente se descarta y degrada esa fuente, mientras las señales coherentes
del mismo resultado continúan. Las categorías se recortan y normalizan con
`casefold`; cuando el refresh pide categoría, el candidato debe coincidir con
esa categoría normalizada. Una source sólo queda como exitosa si publica al
menos una evidencia válida; respuestas vacías o datos descartados no se
confunden con una recopilación efectiva.
