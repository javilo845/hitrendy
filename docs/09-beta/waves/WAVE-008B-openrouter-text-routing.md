# WAVE-008B — OpenRouter real para recomendaciones y texto

## Objetivo

Conectar OpenRouter mediante el provider existente y crear rutas fast/balanced/quality con control de costo.

## Contexto del repositorio


WAVE-001 ya creó provider OpenAI-compatible. No reescribirlo.


## Alcance


- adapter OpenRouter;
- model routes;
- free router;
- structured output;
- usage/cost;
- 402/429;
- fallback explícito.


## Inspección obligatoria

Antes de editar:


- provider content;
- factory;
- prompts/contracts;
- conversations;
- usage;
- capability registry.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Adaptar sin duplicar HTTP client.
2. Configurar rutas por capability/tier.
3. Catálogo cacheado.
4. Evaluaciones.
5. `openrouter/free` para fast zero-cost.
6. Desactivar paid fallback.
7. Registrar modelo real y costo.
8. Mapear 402/429.
9. Smoke opt-in.


## Contratos


Capacidades iniciales: advisor y copywriter. Respuestas Pydantic.


## Pruebas obligatorias


- fake provider;
- free route;
- paid disabled;
- structured JSON;
- multilingual;
- brand words;
- usage;
- smoke con bandera;
- E2E.


## Criterios de aceptación


- [ ] OpenRouter real responde.
- [ ] Fast funciona con ruta autorizada.
- [ ] No gasto no autorizado.
- [ ] Costos registrados.
- [ ] Errores claros.
- [ ] CI pasa.


## Prohibiciones


- No poner API key en frontend.
- No hardcodear modelos sin evaluación.
- No borrar provider fake.


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

## Operación de la ruta OpenRouter

La configuración vive sólo en el backend. `AI_PROVIDER=openrouter` requiere
`OPENROUTER_API_KEY`; el cliente reutiliza el adapter OpenAI-compatible y
llama a `OPENROUTER_BASE_URL` (por defecto `https://openrouter.ai/api/v1`).
La clave nunca se entrega al frontend, se persiste, se incluye en logs de
aplicación ni se refleja en errores.

En staging y producción sólo se aceptan los proveedores textuales reales
`openai-compatible` y `openrouter`; `demo` permanece sólo para desarrollo y
tests. En esos entornos `OPENROUTER_BASE_URL` debe usar HTTPS. La configuración
de `fast` se valida también en la factory para que una modificación directa de
settings no pueda redirigir esa ruta a un modelo pagado.

Las rutas autorizadas son `fast`, `balanced` y `quality` para `advisor` y
`copywriter`. `fast` usa exclusivamente `OPENROUTER_FAST_MODEL=openrouter/free`.
`balanced` y `quality` sólo se anuncian y ejecutan si respectivamente
`OPENROUTER_BALANCED_MODEL` y `OPENROUTER_QUALITY_MODEL` contienen un ID
aprobado por configuración. El cliente no acepta IDs de modelo en el payload.
`ALLOW_PAID_MODEL_FALLBACK=0` sigue siendo el valor predeterminado: no hay
fallback pagado implícito.

Al usar OpenRouter, advisor y copywriter solicitan `response_format` con JSON
Schema estricto (`strict: true`) de sus contratos `AdvisorResponse` y
`GeneratedSocialPost`; `json_object` no se presenta como salida estructurada
equivalente. Los niveles OpenRouter sólo se anuncian para esas dos capacidades:
la revisión visual conserva los niveles de su propio provider.

`openrouter/free` es un router y puede resolver a un modelo físico distinto;
el uso conserva separados el modelo solicitado y el modelo realmente informado
por OpenRouter. Si el proveedor no informa coste, se conserva `null`, nunca
`0`. Los eventos registran tokens, coste Decimal, moneda, request ID y outcome,
sin prompts, respuestas ni secretos.

Una reparación de copywriter se considera una operación lógica: suma los
tokens y el coste Decimal de cada llamada, conserva el modelo solicitado, usa
el modelo y request ID de la última respuesta válida, y conserva coste `null`
si cualquier coste no puede conocerse honestamente. El guion corto usa la misma
política de metadata de texto.

## Catálogo y evaluaciones

El catálogo interno `OpenRouterModelCatalog` consulta `/models` sólo en cache
miss y usa `OPENROUTER_CATALOG_TTL_SECONDS` (3600 por defecto) sobre el store
efímero disponible (memoria en desarrollo/tests o Redis). Una caída o respuesta
inválida del catálogo no bloquea `openrouter/free`; el catálogo no se publica
al frontend ni expone precios internos.

`app.generation.model_evaluation` define un conjunto económico y determinista
para español, inglés y portugués: JSON estructurado, instrucciones, contexto de
negocio, palabras preferidas/prohibidas, caption y recomendación accionable.
CI ejecuta el provider demo. Para evaluar un candidato real de forma opt-in,
instáncialo con un modelo explícitamente aprobado y ejecuta
`evaluate_candidate(provider)` en un entorno con presupuesto controlado; no se
declara un ganador ni se habilita `balanced`/`quality` sin revisar ese resultado.

## Errores y smoke real

Las respuestas 402 se registran como `payment_required`; 429 normal como
`rate_limited`; sólo señales explícitas de quota/crédito como `quota_exhausted`.
El `Retry-After` se propaga únicamente cuando es un número seguro entre 1 y
86400 segundos. Timeouts, 502/503 y JSON/schema inválido se registran con su
outcome operativo y no dejan un resultado o artefacto parcial.
Después de reservar una `Idempotency-Key`, cualquier fallo posterior revierte
los datos incompletos y marca la reserva como `failed` en una transacción
segura; un replay con el mismo payload puede volver a intentar la operación.

El smoke real no corre en CI. Requiere exactamente
`RUN_REAL_AI_SMOKE=1`, `AI_PROVIDER=openrouter` y `OPENROUTER_API_KEY`; hace
una sola llamada mínima de advisor con `fast`/`openrouter/free` y valida el
contrato Pydantic y metadatos disponibles, sin imprimir secretos.
