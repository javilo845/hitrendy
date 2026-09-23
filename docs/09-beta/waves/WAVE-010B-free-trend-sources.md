# WAVE-010B — YouTube, búsqueda y RSS

## Objetivo

Conectar las primeras fuentes compatibles con presupuesto cero o muy bajo.

## Contexto del repositorio


Prioridad de usuario: Google, YouTube, TikTok, Instagram, noticias, Reddit, local. Solo se conectan fuentes legal/técnicamente disponibles.


## Alcance


- YouTube;
- SerpApi;
- RSS allowlist;
- quotas;
- cache;
- source availability.


## Inspección obligatoria

Antes de editar:


- trends adapters;
- config;
- capabilities;
- usage;
- docs.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. YouTube key y quota budget.
2. SerpApi 250/month budget.
3. RSS allowlist.
4. Normalizar.
5. Cache.
6. mensajes quota.
7. atribución.
8. deshabilitar GNews comercial free.


## Contratos


No habilitar sources restricted en producción.


## Pruebas obligatorias


- fixtures;
- quota;
- malformed feed;
- timeout;
- partial run;
- evidence.


## Criterios de aceptación


- [x] YouTube Data API mediante adapter server-side.
- [x] SerpApi `google_trends` mediante endpoint estructurado.
- [x] RSS/Atom únicamente desde allowlist controlada por servidor.
- [x] Presupuestos globales UTC y cache segura.
- [x] Estado público honesto de capability y degradación parcial.

## Operación y configuración

`TREND_ANALYSIS_ENABLED=1` habilita la capacidad. En producción solo se construyen fuentes reales configuradas; los adapters demo de WAVE-010A no se instalan. Una fuente individual se habilita con su flag y, cuando aplica, su clave solo en el entorno del servidor:

```text
YOUTUBE_TRENDS_ENABLED=1
YOUTUBE_API_KEY=
YOUTUBE_SEARCH_DAILY_BUDGET=80
YOUTUBE_CACHE_TTL_SECONDS=900

SERPAPI_TRENDS_ENABLED=1
SERPAPI_API_KEY=
SERPAPI_MONTHLY_BUDGET=200
SERPAPI_CACHE_TTL_SECONDS=1800

RSS_TRENDS_ENABLED=1
RSS_TRENDS_ALLOWLIST=[...]
RSS_CACHE_TTL_SECONDS=900

TRENDS_HTTP_TIMEOUT_SECONDS=10
TRENDS_MAX_RESULTS_PER_SOURCE=10
TRENDS_NEGATIVE_CACHE_TTL_SECONDS=60
RSS_MAX_RESPONSE_BYTES=524288
RSS_DNS_TIMEOUT_SECONDS=3
```

Las claves no se devuelven por API, no entran en URLs de evidencia, logs ni claves de cache. Los límites internos son conservadores y configurables: 80 `search.list` de YouTube por día UTC y 200 búsquedas SerpApi por mes UTC. Son presupuestos de HiTrendy, no una promesa de cuota del proveedor. Una reserva atómica se guarda por `provider`, operación y período antes de la llamada; los cache hits no reservan cuota. Si el presupuesto configurado se reduce durante un período, el límite efectivo pasa a ser el menor entre el valor persistido y el nuevo valor. Los aumentos esperan al período UTC siguiente. La capacidad muestra una fecha de próximo reset cuando el presupuesto interno se agota.

La cache Redis guarda únicamente resultados normalizados y versionados. Su clave incluye fuente, versión del adapter, región, categoría y consulta pública normalizadas, nunca secretos. Éxitos usan el TTL de la fuente y vacíos el TTL negativo. El lease distribuido deriva su TTL del deadline total de la operación más un margen; los demás workers esperan de forma acotada y consultan periódicamente la cache durante toda esa ventana. Si Redis falla, la recolección continúa con coalescing local y el ledger de presupuesto en PostgreSQL sigue aplicándose.

`RSS_TRENDS_ALLOWLIST` es una lista JSON de objetos con `identifier`, `public_name`, `feed_url` HTTPS, `regions`, `categories` y `enabled`. No hay endpoint para introducir feeds. El `identifier` se normaliza con `strip` antes de cualquier validación y debe cumplir `^[a-z0-9][a-z0-9-]{0,62}$`: minúsculas, dígitos y guiones, sin espacios, dos puntos, saltos de línea ni longitudes excesivas, porque forma parte de claves estables de cache y de salud. La detección de duplicados usa el valor normalizado, así que `feed-a` y ` feed-a ` se rechazan como duplicados. El lector valida DNS e IP pública, host y redirects permitidos, puerto, tamaño, tipo de contenido y XML seguro; el deadline total cubre DNS, redirects y lectura incremental del body. No descarga imágenes, adjuntos ni HTML arbitrario. RSS 2.0 y Atom requieren título, enlace público y fecha `published`, `updated` o `pubDate` verificable. Los enlaces de los items se validan sintácticamente y, si son IP literales, contra rangos no públicos; como solo se guardan como evidencia, nunca provocan DNS ni conexiones.

YouTube usa `search.list` con `type=video`, región/lenguaje seguros, `publishedAfter` de siete días, `safeSearch=strict` y un máximo configurado. SerpApi usa una única llamada `engine=google_trends` con `data_type=RELATED_QUERIES`, `geo` (omitido para `GLOBAL`), `hl`, `date=now 7-d` y `no_cache=false`; no hace una segunda llamada para topics. El parser acepta las estructuras oficiales `related_queries.rising/top` y `related_topics.rising/top`, prioriza `extracted_value`, y normaliza números, porcentajes y el sentinel `Breakout`. Solo acepta el `link` HTTPS de `trends.google.com`; ignora `serpapi_link` y construye una URL pública segura si falta ese enlace.

Las reservas de cuota se confirman en una transacción PostgreSQL independiente y corta antes de la llamada HTTP. El lock se libera antes de contactar al proveedor y una reserva no se devuelve si después falla el parsing, la persistencia o el cliente se desconecta. La cache toma un lease distribuido con token y TTL cuando Redis está disponible; tras una espera acotada vuelve a revisar cache. Redis caído degrada a la protección local sin bloquear el refresh.

El lector RSS resuelve DNS fuera del event loop con timeout y valida todas las direcciones IPv4/IPv6. La conexión HTTPS se abre contra una IP validada, conservando el hostname para `Host`, SNI y validación normal de certificado. Cada redirect se resuelve y valida de nuevo; no se acepta `verify=False` ni una resolución posterior privada.

Los flags de fuentes son opcionales: un flag activo sin key o RSS sin feeds enabled deja únicamente esa fuente como `unconfigured`; no impide iniciar la aplicación ni usar otra fuente válida. `GET /trends/sources` requiere workspace y expone de forma segura identificador, nombre público, tipo, configuración, estado y reset de cuota, sin keys, feeds, URLs autenticadas, payloads ni contadores internos. Cada feed RSS aparece con su propio identificador y estado. `EMPTY` indica una fuente saludable que sí fue consultada y no devolvió señales; se muestra como `available`. El estado público se comparte por Redis/Upstash con TTL de cinco minutos y fallback local; un éxito posterior elimina degradación y reset anteriores. La lectura combina el estado compartido y el local y elige el de `observed_at` más reciente, de modo que un fallo de escritura en Redis no puede resucitar una salud vieja; un fallo de lectura solo degrada el uso compartido, nunca la aplicación.

Una fuente que no declara la región o la categoría pedida no es aplicable a ese refresh: no se consulta, no hace DNS ni HTTP, no registra outcome, no cambia su salud runtime, no aparece en `sources_attempted` ni `sources_failed` y no se muestra como caída en `/trends/sources`. No aplicable no es lo mismo que `EMPTY`: una fuente no aplicable simplemente no participa, mientras que `EMPTY` solo se registra tras una consulta real.

Resultados vacíos no son tendencias. Timeouts, payloads inválidos, feeds malformados, rate limiting o cuotas se registran de forma segura por fuente; si otras fuentes aportan evidencia el run queda `partial`. Si ninguna aporta evidencia, queda `failed`. TikTok, Instagram, X, Reddit y GNews no están conectados ni se presentan como disponibles.

## Smoke real opt-in

Nunca se ejecuta en CI. Con una fuente real ya configurada, se puede hacer una consulta por adapter habilitando explícitamente:

```bash
cd starter/backend
RUN_REAL_TRENDS_SMOKE=1 PYTHONPATH=. python -m pytest -m real_trends -q
```

La suite no imprime claves y se salta limpiamente cuando faltan configuración o autorización explícita.


## Prohibiciones


- No usar GNews Free comercial.
- No Reddit comercial sin aprobación.
- No TikTok Research API.


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
