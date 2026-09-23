# Matriz de APIs, costos y restricciones

**Corte de revisión:** 26 de julio de 2026.  
Los planes cambian. El backend deberá guardar la configuración real y el equipo debe revisar precios antes de cada despliegue.

## 1. Respuesta directa

Se puede iniciar una beta cerrada con aproximadamente **ocho piezas sin pago inicial**, pero no todas tienen calidad o términos adecuados para una beta comercial permanente:

1. Supabase Free — PostgreSQL y Storage.
2. Upstash Redis Free.
3. Render Free — backend con cold start y restricciones.
4. OpenRouter free models — texto de bajo volumen.
5. Resend Free — correo transaccional.
6. YouTube Data API — cuota diaria predeterminada.
7. SerpApi Free — 250 búsquedas al mes.
8. Google Sign-In — integración de identidad sin una tarifa por login publicada.

También se pueden usar feeds RSS públicos, pero no constituyen una única API y se deben respetar términos y derechos de cada fuente.

## 2. Clasificación

### Verde — útil para una beta pequeña

| Servicio | Costo inicial | Cuota/condición | Uso propuesto | Riesgo |
|---|---:|---|---|---|
| Supabase Free | $0 | 2 proyectos, 500 MB DB/proyecto, 1 GB Storage, 5 GB egress, 50k MAU | PostgreSQL y archivos | pausa/inactividad, sin backups automáticos |
| Upstash Redis Free | $0 | 256 MB, 10 GB bandwidth, 500k comandos/mes | rate limits, cache, jobs ligeros | no es SLA de producción |
| Resend Free | $0 | 3,000 emails/mes, 100/día, 1 dominio | verificación, reset password | límite diario |
| YouTube Data API | $0 con cuota | 10,000 unidades/día y cuotas por operación | señal de tendencias y videos | cuota y políticas |
| SerpApi Free | $0 | 250 búsquedas/mes | prototipo de Google Search/Trends | volumen muy bajo |
| OpenRouter free router | $0 | modelos gratuitos y rate limits bajos | recomendaciones/texto de demostración | latencia, disponibilidad y modelo variable |

### Amarillo — gratuito con condiciones fuertes

| Servicio | Condición | Decisión |
|---|---|---|
| Render Free | duerme tras 15 minutos, cold start cercano a un minuto, 750 horas; no recomendado para producción | válido para demo/beta cerrada |
| Instagram API | sin tarifa por llamada documentada, pero requiere cuenta profesional, permisos y revisión | integrar después, no contar como fuente de tendencias general |
| Google OAuth | requiere proyecto, credenciales, consentimiento y posible verificación de scopes | usar solo `openid email profile` al inicio |
| Google Trends API | alfa limitada a pocos testers | no usar como dependencia crítica |
| TikTok Content APIs | revisión de app y permisos | no confundir con acceso a tendencias |
| RSS/local sites | puede ser gratis | usar solo fuentes permitidas y atribuidas |

### Naranja — gratis solo para desarrollo/no comercial

| Servicio | Restricción | Decisión |
|---|---|---|
| Vercel Hobby | uso personal no comercial | no elegir para una beta comercial |
| GNews Free | desarrollo/testing, 100 requests/día, 12 h de atraso | deshabilitar en producción comercial |
| Reddit Data API | uso comercial requiere aprobación | no habilitar comercialmente sin permiso |

### Rojo — pago o crédito requerido

| Servicio | Modelo de cobro | Decisión |
|---|---|---|
| X API | consumo/créditos | desactivado por defecto |
| OpenRouter modelos premium | tokens/requests | opt-in con presupuesto |
| OpenRouter imágenes | por generación/uso | WAVE-011 |
| OpenRouter video | por trabajo generado | WAVE-013 |
| Railway después de prueba | crédito/prueba y luego cobro | no tratar como gratuito permanente |
| Proveedores comerciales de noticias | suscripción | evaluar en WAVE-010 |

## 3. Límites de OpenRouter

- Los modelos gratuitos tienen IDs con `:free` o pueden seleccionarse mediante `openrouter/free`.
- La disponibilidad de modelos gratuitos puede cambiar.
- Sin compras suficientes, la cuota diaria gratuita es baja.
- Con al menos $10 de créditos comprados históricamente, OpenRouter documenta una cuota diaria mayor para modelos gratuitos.
- Los modelos gratuitos son adecuados para pruebas y bajo volumen, no para prometer disponibilidad de producción.
- El endpoint de modelos expone capacidades y precios; precio `0` indica gratuito.
- Imágenes y video no deben asumirse gratis.

## 4. Cómo debe saberlo HiTrendy

No basta con variables de entorno. Se necesita un registro de capacidades.

Estados:

```text
available
unconfigured
disabled
restricted
quota_exhausted
payment_required
degraded
error
```

Ejemplo seguro enviado al frontend:

```json
{
  "advisor": {
    "status": "available",
    "tier": "free",
    "quality_levels": ["fast"],
    "message": null,
    "next_reset_at": "2026-07-27T00:00:00Z"
  },
  "image_generation": {
    "status": "payment_required",
    "tier": "paid",
    "quality_levels": [],
    "message": "La generación de imágenes no está habilitada en esta beta."
  },
  "x_trends": {
    "status": "disabled",
    "tier": "paid",
    "message": "X no está conectado."
  }
}
```

La respuesta nunca incluye:

- claves;
- saldo exacto del dueño;
- IDs secretos;
- errores internos;
- credenciales;
- URLs privadas.

## 5. Reglas por capacidad

### Texto gratuito agotado

- No cambiar silenciosamente a un modelo pagado.
- Retornar `AI_QUOTA_EXHAUSTED`.
- Mostrar el siguiente reinicio si se conoce.
- Permitir que un administrador active saldo pagado.

### Imagen no pagada

- Entregar:
  - concepto visual;
  - composición;
  - formato;
  - paleta;
  - prompt;
  - texto del post.
- No crear un placeholder y llamarlo “imagen generada”.

### Video no pagado

- Entregar guion, tomas y storyboard.
- Mantener la acción “Generar video” deshabilitada.

### Tendencias incompletas

- Mostrar fuentes disponibles.
- Etiquetar como recomendaciones si no hay evidencia externa.
- Nunca inventar datos de TikTok, Instagram o X.

## 6. Presupuesto recomendado de beta

Mientras el presupuesto sea desconocido:

```text
USAGE_ENFORCEMENT_MODE=soft
ALLOW_PAID_MODEL_FALLBACK=false
IMAGE_GENERATION_ENABLED=false
VIDEO_GENERATION_ENABLED=false
X_TRENDS_ENABLED=false
```

Configurar un tope mensual antes de activar cualquier fallback pagado.
