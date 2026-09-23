# Guía de Configuración de APIs para Presentación

*Documento técnico para configuración de proveedores de IA. Actualizar `.env` en el backend solo.*

---

## 1. Arquitectura de proveedores

HiTrendy usa proveedores de IA en capa separados. Para una presentación a jueces, la combinación recomendada es:

| Feature | Proveedor | Costo | Por qué |
|---------|-----------|-------|---------|
| **Texto (posts sociales)** | OpenRouter | **$0 USD** | Tier "free" con modelos comunitarios; basta registrarse en openrouter.ai |
| **Imágenes** | OpenAI (DALL-E 3) | ~$0.04/unidad | Pago por imagen generada; calidad alta |
| **Video** | OpenAI (modelo video) | ~$1.00/video | Pago por video generado; 16s o 20s de duración |
| **Tendencias** | RSS (incluido) | **$0 USD** | Fuentes RSS ya configuradas (BBC News); no requiere clave |
| **YouTube** | Google API | **$0 USD** (hasta 10k búsquedas/día) | Cuota gratuita de Google; opcional |

---

## 2. Paso a paso: Obtener cada clave

### 2.1 OpenRouter (texto - GRATIS)

1. Entra a [openrouter.ai](https://openrouter.ai)
2. Haz clic en "Sign up" (registro con GitHub o correo)
3. Después de registrarte, ve a la sección de "API Keys"
4. Haz clic en "Create Key" -> "Create API Key"
5. Copia la clave que empieza por `sk-or-`
6. **Este paso es 100% opcional para el costo**: el sistema funciona en modo demo sin esta clave

### 2.2 OpenAI (imágenes y video - PAGO MÍNIMO)

1. Entra a [platform.openai.com](https://platform.openai.com)
2. Regístrate con correo y agrega tarjeta de crédito (aunque vayas a gastar poco)
3. Ve a "API keys" en el menú lateral
4. Haz clic en "Create new secret key"
5. Copia la clave que empieza por `sk-`
6. **Costo estimado para presentación**: entre $1.50 y $3 USD máximos (ver sección 5)

### 2.3 YouTube API (tendencias - GRATIS)

1. Ve a [console.cloud.google.com](https://console.cloud.google.com)
2. Inicia sesión con cuenta de Google
3. Crea un proyecto (o selecciona uno existente)
4. En el buscador, escribe "YouTube Data API v3" y ábiala
5. Ve a "Credenciales" -> "Crear claves API" -> "Clave API"
6. Copia la clave que empieza por `AIzaSy...`
7. **Costo**: $0 USD; Google otorga 10,000 unidades por día gratis; cada búsqueda de tendencias cuesta 100 unidades

### 2.4 SerpAPI (búsquedas Google - PAGO OPCIONAL)

1. Ve a [serpapi.com](https://serpapi.com)
2. Regístrate; tiene plan free con búsquedas limitadas
3. Si necesitas más búsquedas, hay planes de pago desde $50 USD por 10,000 consultas
4. **Para presentación**: 100% opcional; el modo demo ya trae RSS de BBC News incluido

---

## 3. Configuración en el backend (.env)

Una vez que tengas las claves, agrégalas al archivo `.env` en la raíz del proyecto (solo backend). **Nunca poner claves en el frontend ni en repositorio.**

```
# === OBLIGATORIO PARA IMÁGENES/VIDEO ===
OPENAI_API_KEY=sk-tu-openai-key-aquí

# === OPCIONALES - TEXTOS ===
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-tu-key-aquí  # Si no la pusiste, usa modo demo
OPENROUTER_FAST_MODEL=openrouter/free

# === TENDENCIAS - YOUTUBE OPCIONAL ===
YOUTUBE_API_KEY=AIzaSy...  # Si no la pusiste, usa modo RSS
YOUTUBE_TRENDS_ENABLED=1    # Pone 1 solo si tienes la clave anterior

# === LO QUE YA VENÍA POR DEFECTO (no toques) ===
AI_PROVIDER=demo           # Default si no hay configuración
AI_BASE_URL=https://api.openai.com/v1
IMAGE_GENERATION_ENABLED=0  # Se activa poniendo 1 si tienes OPENAI_API_KEY
```

---

## 4. Qué es 100% opcional (no necesitas tocar)

Lo siguiente **no es necesario** para que la presentación funcione:

| Elemento | Por qué es opcional |
|----------|---------------------|
| `OPENROUTER_API_KEY` | El sistema tiene modo `AI_PROVIDER=demo`; los posts de texto serán simulados pero el flujo completo funciona |
| `YOUTUBE_API_KEY` | El sistema tiene `RSS_TRENDS_ENABLED=1` por defecto (incluye BBC News); YouTube es extra |
| `SERPAPI_API_KEY` | No necesario; tendencias vienen de RSS o modo demo |
| `IMAGE_GENERATION_ENABLED=1` | Se deja en 0 (demo) si no quieres gastar en imágenes; el modo muestra visual brief en su lugar |
| `VIDEO_GENERATION_ENABLED=1` | Se deja en 0 (demo) si no quieres gastar en video; el modo muestra storyboard simulado |

**Configuración mínima para presentación funcional:**
Sólo necesitas `OPENAI_API_KEY` si quieres imágenes y video reales. Si lo dejas vacío, todo está en modo demo y funciona cero costos.

---

## 5. Presupuesto máximo estimado

Para una exposición a jueces con generación real (texto + imágenes + 1 video):

| Item | Cantidad | Costo unitario | Total |
|------|----------|----------------|-------|
| **Generaciones de texto** | 20 llamadas | $0 (OpenRouter free) | **$0** |
| **Generaciones de imágenes** | 5 imágenes | $0.04 cada una | **$0.20** |
| **Generaciones de video** | 1 video corto | $1.00 | **$1.00** |
| **YouTube API** | Incluido en cuota gratuita | $0 | **$0** |
| **TOTAL MÁXIMO** | | | **~$1.20 USD** |

**Escenario "conservador" (solo imágenes, sin video):**
- 5 imágenes a $0.04 = **$0.20 USD**

**Escenario "demo total":**
- Cero configuración de API
- Costo: **$0 USD**

---

## 6. Guión rápido para explicar a jueces

> "Nuestro sistema usa tres tipos de IA:
>
> 1. **Texto**: Usamos OpenRouter con modelo gratuito; cuesta $0 y genera posts sociales.
> 2. **Imágenes**: Usamos OpenAI DALL-E 3; el costo por imagen es mínimo (~$0.04). En esta demostración hemos generado 5 imágenes por un costo total de menos de $0.20 USD.
> 3. **Video**: Usamos OpenAI para video generativo; 1 video corto cuesta aproximadamente $1.00 USD.
> 4. **Tendencias**: Usamos fuentes RSS (incluye BBC News); costo $0. Si el usuario quiere, puede conectar su clave YouTube API (también gratuita, 10,000 búsquedas por día).
>
> **Costo total de esta presentación**: menos de $1.50 USD. El sistema está diseñado para funcionar en modo demo cero costos si es necesario."

---

## 7. Pasos finales después de configurar

1. Guarda el `.env` en la raíz del backend
2. Reinicia el servidor backend: `npm run backend:dev` (o `python -m uvicorn app.main:app --reload --port 8000`)
3. La app detectará las claves automáticamente
4. Prueba los endpoints:
   - `GET /api/v1/capabilities` → debe mostrar `image_generation: enabled` y `video_generation: enabled` si pusiste `OPENAI_API_KEY`
   - `GET /api/v1/trends/home` → mostrará tendencias RSS si `RSS_TRENDS_ENABLED=1`

---
*Fin de la guía. Para dudas sobre algún paso específico, consultar la documentación en `docs/06-implementation/provider-keys.md`.*