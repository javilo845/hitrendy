# Motor de tendencias verificables

## 1. Definición

Una tendencia es un tema con evidencia externa reciente. Una recomendación es una idea derivada del negocio. No son sinónimos.

## 2. Fuentes por prioridad

Decisión del producto:

1. búsqueda de Google;
2. YouTube;
3. TikTok;
4. Instagram;
5. noticias;
6. Reddit;
7. sitios locales.

Disponibilidad técnica real para primera versión:

### Activables

- SerpApi Free para prototipo de Google Search/Trends.
- YouTube Data API.
- RSS y sitios locales permitidos.

### Condicionales

- Google Trends oficial: alfa limitada.
- Noticias comerciales: requieren plan válido.
- Instagram profesional: datos de cuenta autorizada, no firehose global.
- TikTok: Research API no disponible para uso comercial.
- Reddit comercial: requiere aprobación.
- X: pago por consumo.

## 3. Primera versión honesta

```text
YouTube
+ Search/Trends provider
+ RSS local
→ candidatos
→ deduplicación
→ scoring
→ personalización
```

No incluir TikTok/Instagram/X como fuente automática hasta tener acceso válido.

El usuario sí puede proporcionar enlaces manualmente para análisis.

## 4. Interfaz de fuentes

```python
class TrendSource(Protocol):
    key: str
    async def availability(self) -> SourceAvailability: ...
    async def collect(self, query: TrendQuery) -> list[TrendEvidence]: ...
```

`TrendEvidence`:

```json
{
  "source": "youtube",
  "external_id": "...",
  "url": "...",
  "title": "...",
  "published_at": "...",
  "observed_at": "...",
  "region": "HN",
  "language": "es",
  "metrics": {}
}
```

## 5. Pipeline

1. Construir términos desde categoría, producto, ubicación y plataformas.
2. Recolectar por región LATAM.
3. Normalizar idioma y timestamps.
4. Agrupar semánticamente sin perder evidencia.
5. Calcular crecimiento/frescura.
6. Cruzar fuentes.
7. Filtrar spam y temas inseguros.
8. Calcular relevancia del negocio.
9. Generar explicación con LLM.
10. Persistir evidencia y resultado.

## 6. Scoring inicial

```text
30% crecimiento
25% relevancia al negocio
15% frescura
15% coincidencia regional
10% presencia en varias fuentes
 5% ajuste a plataforma
```

Los pesos deben estar en configuración y versionados.

## 7. Frecuencia

- Job diario.
- Botón de actualización manual.
- Cooldown por negocio.
- Reusar resultados regionales.
- No hacer una recolección completa por cada usuario.

## 8. Home

Cada tarjeta:

- tema;
- fuente(s);
- fecha;
- región;
- confianza;
- razón de relevancia;
- ideas;
- botón “Crear post”;
- enlaces.

Cuando no hay fuentes:

```text
Recomendaciones para tu negocio
```

No:

```text
Tendencias de hoy
```

## 9. Cuotas

- Source adapter consulta capability registry.
- Presupuesto por ejecución.
- Cache.
- Límite por día.
- Si SerpApi llega a 250 búsquedas, marcar agotado.
- YouTube usa presupuesto de cuota.
- Fuentes deshabilitadas no bloquean el pipeline completo.

## 10. Seguridad y cumplimiento

- Respetar términos.
- Guardar extractos mínimos.
- No republicar artículos completos.
- Atribuir URL y fecha.
- Permitir borrar evidencia de usuario.
- No scraping oculto.
- No evadir bloqueos.
- No afirmar acceso oficial cuando es indirecto.

## 11. Pruebas

- adapters fake.
- deduplicación.
- scoring determinista.
- fuente agotada.
- ejecución parcial.
- no trend without evidence.
- enlaces y timestamps.
- aislamiento regional.
- job diario idempotente.
- manual cooldown.
