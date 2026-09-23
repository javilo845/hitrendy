# Uso, costos y administración

## 1. Objetivo

Mostrar desgaste durante la demostración sin imponer cobro todavía y sin crear una puerta trasera.

## 2. Modos

```text
off   → registrar, no mostrar ni bloquear
soft  → registrar, mostrar y advertir
hard  → registrar y bloquear
```

Beta inicial:

```text
USAGE_ENFORCEMENT_MODE=soft
```

## 3. Unidades

Separadas:

- recomendaciones;
- textos;
- imágenes;
- videos;
- refresh de tendencias.

No presentar tokens al usuario. Mostrar unidades comprensibles.

## 4. Ledger

Cada operación exitosa o facturable crea `usage_event`.

No recalcular solo desde logs. No editar eventos históricos.

## 5. UI

Configuración → Uso:

- barra del periodo;
- usado/restante;
- fecha de reinicio;
- desglose;
- advertencias;
- capacidades deshabilitadas.

En soft mode, llegar a cero no bloquea, pero la UI muestra el estado de demostración.

## 6. Herramienta administrativa

No usar comando secreto incrustado en el navegador.

CLI:

```bash
python -m app.admin.usage reset \
  --email demo@example.com --actor ops@example.com \
  --reason "feria" --confirm RESET_USAGE
```

Requisitos:

- solo entorno autorizado;
- requiere credencial/admin;
- confirmación;
- escribe `usage_adjustment`;
- registra actor, fecha y motivo;
- nunca imprime API keys;
- tests.

Panel administrativo futuro:

```text
/admin/usage
```

No enlazado para usuarios normales y protegido por rol real, no por URL oculta.

## 7. Control de gasto

Variables:

```text
ALLOW_PAID_MODEL_FALLBACK=false
MONTHLY_AI_BUDGET_USD=0
MAX_TEXT_COST_USD=...
MAX_IMAGE_COST_USD=...
MAX_VIDEO_COST_USD=...
```

Antes de ejecutar:

1. Resolver capacidad.
2. Verificar allowance.
3. Verificar costo máximo conocido.
4. Reservar uso estimado.
5. Ejecutar.
6. Registrar costo real.
7. Reconciliar reserva.

## 8. Reglas

- Sin saldo: no ejecutar capacidad pagada.
- 402: `payment_required`.
- 429: `quota_exhausted` o `rate_limited`.
- No hacer fallback pagado.
- El usuario no ve el saldo del dueño.
- El administrador ve costo agregado.
- Nunca permitir costo ilimitado de video.

## 9. Pruebas

- soft mode.
- hard mode.
- reset auditado.
- usuario no admin rechazado.
- reserva concurrente.
- costo real.
- cuota agotada.
- periodo reiniciado.
