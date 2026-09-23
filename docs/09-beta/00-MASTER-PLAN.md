# Plan maestro de beta

## 1. Norte del producto

HiTrendy será un asistente de marketing para pequeños negocios. La beta no se medirá por la cantidad de pantallas ni de APIs, sino por completar correctamente este recorrido:

```text
crear cuenta
→ describir el negocio
→ confirmar la marca
→ recibir recomendaciones útiles
→ generar un post para Instagram
→ guardar el resultado
```

La promesa principal no es “acceso a muchas IAs”. La promesa es transformar el contexto de un negocio en contenido útil con la menor fricción posible.

## 2. Lo que ya está resuelto

Las cinco waves anteriores fortalecieron la base:

- Providers reales y configuración de runtime.
- Migraciones y seeds PostgreSQL.
- Reintentos idempotentes.
- E2E reales con PostgreSQL.
- CI para backend, frontend, migraciones y E2E.

Por eso la siguiente etapa no debe rehacer infraestructura. Debe conectar el producto real.

## 3. Bloques del plan

### Bloque A — Identidad real

- Registro temporal seguro.
- Onboarding obligatorio.
- Finalización atómica de cuenta, workspace interno, negocio, marca y sesión.
- Inicio con Google.
- Eliminación del modo demo de la experiencia pública.
- Guardas de rutas para onboarding incompleto.

### Bloque B — Persistencia y nube

- PostgreSQL administrado.
- Storage S3 compatible.
- Redis administrado.
- Backend y frontend desplegados.
- Cookies, CORS y CSRF correctos.
- Migraciones controladas.

### Bloque C — IA textual real

- OpenRouter.
- Router por capacidad.
- Modos rápido/equilibrado/calidad.
- Recomendaciones.
- Captions y posts.
- Registro de uso y costo.
- Degradación explícita cuando no hay cuota o dinero.

### Bloque D — Cuenta y configuración

- Datos personales.
- Negocio.
- Marca.
- Idiomas.
- Uso.
- Privacidad.
- Eliminación de cuenta.
- Administración auditada.

### Bloque E — Tendencias verificables

- Adaptadores por fuente.
- Datos con fecha, URL y región.
- Normalización y scoring.
- Recomendaciones personalizadas.
- Ejecución diaria y manual.
- Nunca convertir conocimiento general del LLM en “tendencia detectada”.

### Bloque F — Multimedia

- Imágenes después de cerrar texto.
- Conexiones sociales después de cerrar tendencias.
- Video como función avanzada y pagada.

## 4. Orden de implementación

```text
006A  Pending signup y finalización atómica
006B  Onboarding frontend y eliminación del demo público
006C  Google Sign-In
007A  Supabase PostgreSQL, Storage y Redis
007B  Despliegue beta, cookies, CORS y CSRF
008A  Registro de capacidades y estado de proveedores
008B  OpenRouter de texto y niveles de calidad
008C  Flujo “post de Instagram en cinco minutos”
009   Configuración, idiomas, uso y ciclo de cuenta
010A  Contrato de fuentes de tendencias
010B  YouTube + búsqueda/Trends + RSS
010C  Jobs diarios y pantalla Inicio
011   Generación de imágenes
012   Conexiones con redes propias
013   Generación de video
014   Preparación de beta cerrada
```

Cada subwave debe terminar con pruebas, documentación y reporte. No se deben combinar varias subwaves en un commit gigante.

## 5. Perfiles de costo

### Perfil `beta-zero-cost`

Adecuado para demostraciones y pocos usuarios:

- Supabase Free.
- Render Free para backend, aceptando cold starts.
- Upstash Redis Free.
- OpenRouter free router para texto.
- Resend Free.
- YouTube Data API con cuota predeterminada.
- SerpApi Free para una muestra pequeña.
- RSS permitido.

Limitaciones:

- El modelo gratuito puede cambiar o estar saturado.
- No se habilitan imágenes ni video reales.
- GNews gratis no se usa en una beta comercial.
- X se desactiva.
- TikTok/Instagram no se presentan como fuentes completas de tendencias.
- El backend puede tardar alrededor de un minuto en despertar si se usa Render Free.

### Perfil `beta-controlled-paid`

Adecuado para beta externa más confiable:

- Supabase Pro o la misma base Free con vigilancia y backups propios.
- Hosting sin cold starts.
- OpenRouter con saldo y límites.
- Proveedor comercial de noticias/búsqueda.
- Presupuesto máximo mensual.
- Imágenes habilitadas solo con créditos.
- Video desactivado inicialmente.

## 6. Reglas de degradación

La beta debe seguir siendo honesta cuando falta una integración:

| Capacidad ausente | Comportamiento |
|---|---|
| Modelo de texto pagado | Usar modelo gratuito permitido o bloquear con mensaje claro |
| Generación de imagen | Entregar briefing visual, formato y prompt; no fingir imagen |
| Video | Entregar guion y storyboard |
| Fuentes de tendencias | Mostrar “recomendaciones para tu negocio”, no “tendencias” |
| X sin créditos | Omitir X y señalar fuente no disponible |
| TikTok sin aprobación | Aceptar enlaces/manual input; no simular acceso |
| Noticias comerciales sin plan | Deshabilitar en producción |
| Cuota agotada | Mostrar siguiente reinicio y opciones disponibles |

## 7. Definición de terminado de la beta textual

- Registro y login funcionan desde una URL pública.
- El onboarding no usa solo `localStorage`.
- Existe exactamente un negocio activo por cuenta.
- Producción no permite provider demo.
- OpenRouter responde realmente.
- Se guarda el modelo, modalidad, tokens y costo reportado.
- La IA recibe contexto de negocio.
- La respuesta puede guardarse y recuperarse.
- La aplicación conoce qué capacidades están configuradas.
- No se filtran secretos al cliente.
- Tests unitarios, E2E y CI pasan.
- Se ha probado una cuenta nueva desde navegador incógnito.
