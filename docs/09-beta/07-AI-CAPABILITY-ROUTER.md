# Router de capacidades de IA

## 1. Objetivo

Separar “qué quiere hacer el usuario” de “qué proveedor/modelo está disponible”.

Capacidades iniciales:

```text
advisor
copywriter
vision_review
image_generation
video_generation
trend_analysis
```

Niveles:

```text
fast
balanced
quality
```

## 2. Regla principal

El usuario elige nivel, no modelo. El administrador define rutas aprobadas.

Ejemplo:

```text
advisor/fast       → OpenRouter free route
advisor/balanced   → modelo pagado A
advisor/quality    → modelo pagado B
copywriter/fast    → modelo estructurado económico
```

## 3. Registro de capacidades

Servicio interno:

```python
class CapabilityRegistry:
    async def get_public_snapshot(self, principal) -> PublicCapabilities: ...
    async def resolve(self, capability, quality_tier) -> ResolvedRoute: ...
    async def record_outcome(self, route, outcome) -> None: ...
```

Estados:

- `available`
- `unconfigured`
- `disabled`
- `restricted`
- `quota_exhausted`
- `payment_required`
- `degraded`
- `error`

## 4. Endpoint público seguro

```http
GET /api/v1/capabilities
```

Debe responder solo lo que la UI necesita:

- si está disponible;
- niveles permitidos;
- mensaje;
- reinicio de cuota;
- fallback funcional.

No exponer slug técnico por defecto. Puede enviarse un `route_label` interno solo a admins.

## 5. Contexto para el LLM

La IA debe saber qué puede ofrecer, pero no necesita conocer secretos ni saldo monetario.

Bloque interno:

```json
{
  "available_actions": {
    "text_post": true,
    "image_generation": false,
    "video_generation": false,
    "trend_sources": ["youtube", "search"]
  },
  "unavailable_actions": {
    "x_trends": "not_configured",
    "video_generation": "payment_required"
  }
}
```

Reglas del system prompt:

- No decir “ya generé una imagen” si la capacidad está deshabilitada.
- No citar tendencias de una fuente ausente.
- Ofrecer el fallback permitido.
- No revelar mensajes internos de facturación.
- No sugerir que el usuario compre saldo del dueño del sistema.

## 6. OpenRouter

Integración:

- Base URL OpenAI-compatible.
- API key solo backend.
- `HTTP-Referer` y título configurables.
- Catálogo `/models` cacheado.
- Fijar rutas aprobadas en DB/config.
- Verificar modalidad y parámetros.
- Detectar precio `0` para rutas gratuitas.
- Registrar modelo real usado si el free router lo reporta.
- No usar fallback pagado sin bandera explícita.

## 7. Selección de modelos

No hardcodear una lista eterna. En cada revisión:

1. Consultar catálogo.
2. Filtrar por modalidad.
3. Filtrar por structured outputs cuando aplique.
4. Filtrar por costo máximo.
5. Ejecutar evaluación con casos de HiTrendy.
6. Aprobar manualmente rutas.
7. Guardar versión de evaluación.

Casos de evaluación:

- recomendación de negocio;
- caption en español;
- caption en portugués;
- JSON válido;
- respeto de palabras prohibidas;
- CTA;
- no inventar tendencias;
- latencia;
- costo.

## 8. Contratos de salida

### Recomendación

```json
{
  "summary": "...",
  "reasoning_summary": "...",
  "ideas": [],
  "assumptions": [],
  "source_mode": "business_context"
}
```

### Post

```json
{
  "platform": "instagram",
  "headline": "...",
  "caption": "...",
  "cta": "...",
  "hashtags": [],
  "visual_brief": {
    "format": "4:5",
    "subject": "...",
    "composition": "...",
    "on_image_text": "..."
  }
}
```

Validar con Pydantic. Reparar JSON solo una vez; no aceptar texto libre silenciosamente.

## 9. Costos y eventos

Registrar:

- capability;
- tier;
- provider;
- model;
- tokens;
- costo informado;
- latency;
- status;
- fallback;
- request ID.

## 10. Fallbacks

```text
paid balanced unavailable
→ approved free route, solo si ALLOW_FREE_FALLBACK=true
→ o error transparente
```

Nunca:

```text
free quota exhausted
→ paid model sin autorización
```

## 11. Pruebas

- registry status.
- public snapshot sanitizado.
- model resolution.
- no paid fallback.
- free route.
- 402 payment required.
- 429 quota.
- degraded provider.
- unavailable image fallback.
- prompt capability context.
- structured output.
- usage ledger.
