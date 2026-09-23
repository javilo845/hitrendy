# HiTrendy — Guía para cambiar colores, tipografías y textos

**Para:** cualquiera del equipo, sepa programar o no.
**Sirve para:** contestar en vivo un "cámbieme el color de ese botón" sin tocar
código de la aplicación y sin riesgo de romper nada.

---

## 1. La idea en una frase

**Ningún componente de HiTrendy escribe un color.** Todos piden un *rol*
(`--primary`, `--shell-card`, `--auth-link`) y ese rol se resuelve en un solo
archivo. Cambiás el archivo, cambia toda la aplicación de golpe.

Ese archivo es:

```
starter/web/app/tokens.css
```

Si en la revisión te preguntan "¿y si quiero cambiar la identidad visual?", la
respuesta correcta no es "buscamos los botones". Es: **"se cambian 15 líneas en
un solo archivo; el resto del sistema se recalcula solo, y los contrastes de
accesibilidad ya están documentados ahí"**. Eso es lo que hace que se vea serio.

---

## 2. Cómo está organizado el archivo (5 capas)

| Capa | Qué contiene | ¿Se toca? |
|---|---|---|
| **1. Paleta de marca** | Los colores reales: `--ht-purple: #7c3aed` | **Sí. Aquí se toca todo.** |
| 2. Rampa derivada | Mezclas calculadas de la capa 1 | Solo si sabés lo que hacés |
| 3. Roles semánticos | `--primary`, `--background`, `--border` | Solo si querés reasignar |
| 4. Superficies | Landing, login, encuesta, app, chat | Casos puntuales |
| 5. Componentes | Bordes redondeados, sombras, tipografía, animación | Sí, es seguro |

**Regla:** para el 90% de los pedidos, tocás **solo la capa 1**.

---

## 3. Las 12 perillas seguras

Estas son las líneas que podés cambiar con confianza. Están todas al inicio de
`tokens.css`:

| Variable | Qué pinta en la app |
|---|---|
| `--ht-purple` | **El color principal.** Botones primarios, foco, navegación activa |
| `--ht-purple-deep` | El primario cuando pasás el mouse encima |
| `--ht-purple-bright` | El extremo claro de los degradados |
| `--ht-purple-light` / `--ht-purple-soft` | Acentos suaves, textos secundarios en fondo oscuro |
| `--ht-navy` / `--ht-navy-deep` | Los azules oscuros: landing, encabezados |
| `--ht-ink` | El color del texto principal |
| `--ht-paper` | El fondo claro de toda la app |
| `--ht-white` | Blanco de tarjetas |
| `--ht-pink` | Acento rosado (botón de grabar voz) |
| `--ht-error` | Rojo de errores |
| `--ht-success` / `--ht-warning` | Verde y ámbar de estados |

Y en la capa 5, además:

| Variable | Qué controla |
|---|---|
| `--radius-lg`, `--radius-pill` | Qué tan redondeados son botones y tarjetas |
| `--font-heading` / `--font-body` | Las tipografías (ver sección 6) |
| `--duration-base` | Velocidad de las animaciones |

---

## 4. Receta en vivo: "cámbieme el color de ese botón"

Cuatro pasos, dura menos de un minuto delante del jurado:

1. **Clic derecho sobre el botón → Inspeccionar.**
2. En el panel de estilos vas a ver algo como `background: var(--primary)`.
   Ese nombre entre `var(...)` es la respuesta.
3. Abrí `starter/web/app/tokens.css`, buscá ese nombre con `Ctrl+F`. Vas a ver
   que apunta hacia arriba, a un color de la capa 1 (`--ht-purple`).
4. Cambiá el valor hexadecimal ahí y guardá. **La página se actualiza sola**
   (Next.js recarga en caliente, no hay que reiniciar nada).

> **Truco para la demo:** si querés probar sin tocar archivos, en DevTools podés
> editar la variable sobre `:root` en vivo y se recolorea la app entera al
> instante. Es un momento vistoso y demuestra que el sistema es real.

**Lo que NO hay que hacer:** buscar el archivo del botón y escribirle un
`#ff0000`. Eso rompe la regla del proyecto, desincroniza el modo oscuro y es
justo lo que un evaluador va a marcar como deuda técnica.

---

## 5. Sobre la idea del JSON

Lo pensé y hay tres caminos:

### Opción A — Documentar `tokens.css` tal como está *(la recomendada)*
- Costo: **cero**. Ya funciona hoy.
- Recarga en caliente inmediata.
- Los comentarios del archivo ya explican los ratios de contraste — eso es un
  argumento fuerte en la revisión.
- Contra: es CSS, no JSON. Pero son 15 líneas de `--nombre: #color;`, que se lee
  igual de fácil que un JSON.

### Opción B — `theme.json` + un script que regenera `tokens.css`
- `npm run tema` lee un `theme.json` y reescribe el bloque de la capa 1.
- Ventaja: el archivo que toca la persona es literalmente un JSON de 15 claves,
  y es **imposible** romper el CSS porque no lo escribe a mano.
- Contra: hay que acordarse de correr el comando; si alguien edita el CSS
  directo, el JSON queda desactualizado.
- Es la opción más vistosa para presentar ("mirá, un solo JSON").

### Opción C — Leer el JSON en tiempo de ejecución
- `layout.tsx` inyecta las variables desde el JSON en cada carga.
- Contra: trabajo real, riesgo de parpadeo al cargar, y **ya no podés usar
  DevTools para probar en vivo**. No lo vale.

**Mi recomendación:** quedate con **A** para la revisión. Si querés el efecto
"un solo JSON", agregamos **B** después — son ~40 líneas de script y no cambia
nada del funcionamiento actual. Decime y lo armo.

---

## 6. Cambiar las tipografías

Se tocan **dos** lugares:

1. `starter/web/app/layout.tsx` — ahí se importan `Inter` y `Poppins` desde
   Google Fonts. Cambiás el nombre en el `import` y en la llamada.
2. `starter/web/app/tokens.css` — `--font-heading` y `--font-body`.

---

## 7. Cambiar textos

Los textos visibles **no están en los componentes**, están centralizados:

| Archivo | Qué contiene |
|---|---|
| `starter/web/lib/i18n.ts` | La mayoría de los textos de la interfaz |
| `starter/web/lib/instagram-flow-copy.ts` | Textos del flujo de Instagram |
| `starter/web/lib/trends-copy.ts` | Textos de la sección de tendencias |
| `starter/web/lib/labels.ts` | Etiquetas cortas y reutilizadas |

Buscá la frase con `Ctrl+Shift+F` (buscar en todo el proyecto), cambiala, guardá.
Todo el texto visible va en **español**; solo los identificadores técnicos van en
inglés.

---

## 8. Los colores por negocio (distinto de lo anterior)

Ojo con no confundir dos cosas:

- **Tema de la aplicación** → `tokens.css`. Es la marca HiTrendy.
- **Paleta del negocio del usuario** → `starter/web/lib/brand-defaults.ts`.
  Son los colores que HiTrendy le sugiere a *cada cliente* para su contenido, y
  el usuario los edita desde la app. No afectan el aspecto de la interfaz.

---

## 9. Límite conocido (decilo si preguntan)

Quedan unos 80 colores escritos a mano fuera del sistema de tokens, en:

```
app/projects/[id]/page.tsx
app/library/page.tsx
components/landing/about-collage.tsx
components/generated-artifact-card.tsx
components/advisor-response-card.tsx
components/projects/project-folder-card.tsx
lib/plan-export.ts        (PDF exportado — es legítimo, el PDF no tiene CSS)
lib/demo-data.ts          (datos de ejemplo — también legítimo)
```

Esos no cambian al tocar `tokens.css`. Si te lo señalan, la respuesta honesta es:
**"está identificado como deuda técnica; el sistema de tokens cubre toda la
interfaz principal y esas pantallas están en la lista para migrar"**. Reconocer
un límite con precisión se ve mucho mejor que decir que no existe.

---

## 10. Checklist antes de dar por buena una revisión

- [ ] La app sigue levantando (`npm run dev` en `starter/web`)
- [ ] Se ve bien en modo claro **y** en la app autenticada (que usa el tema oscuro)
- [ ] El texto sigue siendo legible sobre el fondo nuevo
- [ ] `npm run typecheck` no da errores
