# 🗺️ Mapa Completo de Rutas, Pantallas y Textos de HiTrendy

Esta guía te muestra **dónde está exactamente cada texto, titular, botón y componente de cada pantalla** para que puedas modificar cualquier frase o diseño al instante.

> 💡 **Tip:** Puedes hacer `Ctrl + Clic` sobre cualquier archivo para abrirlo directamente en tu editor.

---

## 🎨 0. Textos Globales, Colores y Barra Lateral

| Elemento Visual | Texto que muestra en pantalla | Dónde cambiar el texto | Dónde cambiar colores/diseño |
| :--- | :--- | :--- | :--- |
| **Logo de la Marca** | `HiTrendy` *(con el ícono SVG)* | [`starter/web/components/brand/logo.tsx`](./starter/web/components/brand/logo.tsx#L21) | [`starter/web/app/tokens.css`](./starter/web/app/tokens.css) |
| **Barra Superior (Breadcrumb)** | `HiTrendy › [Nombre Sección]` | [`starter/web/components/shell/app-shell.tsx`](./starter/web/components/shell/app-shell.tsx#L195) | [`starter/web/app/globals.css`](./starter/web/app/globals.css) |
| **Menú Lateral (Sidebar)** | `Studio`, `Dashboard`, `Tendencias`, `Plantillas`, `Configuración`, `Cerrar sesión` | [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L40-L46) | [`starter/web/components/shell/app-shell.tsx`](./starter/web/components/shell/app-shell.tsx) |
| **Paleta de Colores y Fondos** | Colores globales, gradientes y temas | — | [`starter/web/app/tokens.css`](./starter/web/app/tokens.css) |

---

## 🌐 1. Portada y Autenticación (Públicas)
150114210
| Pantalla | Texto / Elemento que ves en pantalla | Archivo donde se cambia |
| :--- | :--- | :--- |
| **Landing (Portada)** | • Titular principal: `Comienza a Crear`<br>• Botón CTA con ícono: `Empezar a Crear` | [`starter/web/app/page.tsx`](./starter/web/app/page.tsx#L20-L29) |
| **Landing (Caja de Texto)** | • Placeholder: `Describe qué quieres crear para tu negocio...`<br>• Ejemplos sugeridos: *"Lanzamiento de cafetería"*, *"Post para tienda"* | [`starter/web/components/landing/hero-composer.tsx`](./starter/web/components/landing/hero-composer.tsx#L9-L35) |
| **Iniciar Sesión (`/login`)** | • Título: `Iniciar sesión`<br>• Botón principal: `Entrar`<br>• Botón: `Continuar con Google` | [`starter/web/app/login/page.tsx`](./starter/web/app/login/page.tsx)<br>y [`starter/web/components/auth/auth-card.tsx`](./starter/web/components/auth/auth-card.tsx) |
| **Registro (`/register`)** | • Título: `Crea tu cuenta`<br>• Botón: `Crear cuenta` | [`starter/web/app/register/page.tsx`](./starter/web/app/register/page.tsx) |
| **Recuperar Clave (`/reset-password`)** | • Título: `Recuperar contraseña`<br>• Botón: `Enviar enlace` | [`starter/web/app/reset-password/page.tsx`](./starter/web/app/reset-password/page.tsx) |



## 🤖 2. Studio / Chat de IA (`/studio/new` y `/studio/[id]`)

| Sección / Elemento | Texto que ves en pantalla | Dónde se cambia el texto |
| :--- | :--- | :--- |
| **Pantalla de Bienvenida** | • Título principal: `¿Qué haremos hoy?`<br>• Subtítulo: `Cuéntame qué necesitas y construiremos la idea paso a paso.` | [`starter/web/components/studio/studio-workspace.tsx`](./starter/web/components/studio/studio-workspace.tsx#L925-L936) |
| **Botones de Sugerencia Rápida** | • `Auditar diseño y sugerir Canva`<br>• `Crear publicación para redes`<br>• `Planear contenido de la semana` | [`starter/web/components/studio/studio-workspace.tsx`](./starter/web/components/studio/studio-workspace.tsx#L89-L111) |
| **Barra de Prompt (Composer)** | • Placeholder: `Escribe tu idea o pregunta…`<br>• Texto inferior: `Pega una captura con Ctrl+V, arrástrala aquí o usa +...` | [`starter/web/components/assistant/composer.tsx`](./starter/web/components/assistant/composer.tsx)<br>y [`starter/web/components/studio/studio-workspace.tsx`](./starter/web/components/studio/studio-workspace.tsx#L914-L917) |
| **Burbujas del Chat Activo** | Mensajes de usuario y respuestas en formato Markdown de la IA | [`starter/web/components/assistant/message-list.tsx`](./starter/web/components/assistant/message-list.tsx) |
| **Tarjeta de Propuesta / Post** | • Badge: `PROPUESTA GENERADA`<br>• Botones: `Guardar proyecto`, `Copiar contenido`, `Más corto`, `Más juvenil`, `Más profesional` | [`starter/web/components/generated-artifact-card.tsx`](./starter/web/components/generated-artifact-card.tsx#L147-L255) |
| **Tarjeta de Canva** | • Título: `Plantilla Canva para...`<br>• Botón: `🚀 Abrir en Canva ↗` | [`starter/web/components/generated-artifact-card.tsx`](./starter/web/components/generated-artifact-card.tsx#L168-L190) |
| **Tarjeta de Asesoría Estratégica** | • Badge: `💡 Plan de Contenido & Asesoría`<br>• Botón: `Descargar PDF`<br>• Título: `Estrategia Recomendada` | [`starter/web/components/advisor-response-card.tsx`](./starter/web/components/advisor-response-card.tsx#L71-L87) |

---

## 📊 3. Dashboard / Panel de Control (`/dashboard`)

| Sección / Elemento | Texto que ves en pantalla | Dónde se cambia el texto |
| :--- | :--- | :--- |
| **Cabecera del Dashboard** | • Eyebrow: `DASHBOARD`<br>• Título: `Tu espacio creativo`<br>• Subtítulo: `Organiza proyectos y encuentra una plantilla...`<br>• Pestañas: `Proyectos` y `Plantillas` | En [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L66-L72)<br>*(Renderizado en [`starter/web/app/dashboard/page.tsx`](./starter/web/app/dashboard/page.tsx#L205-L233))* |
| **Banner Héroe Destacado** | • Eyebrow: `EMPIEZA A DISEÑAR`<br>• Titular: **`Todo tu contenido, en un solo lugar.`**<br>• Párrafo descriptivo<br>• Botón: `Crear en Studio →` | En [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L74-L82)<br>*(Renderizado en [`starter/web/app/dashboard/page.tsx`](./starter/web/app/dashboard/page.tsx#L240-L253))* |
| **Sección de Tus Proyectos** | • Título: `Tus proyectos`<br>• Filtros: `Activos` / `Archivados`<br>• Buscador: `Buscar proyectos...` | En [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L73-L86)<br>*(Renderizado en [`starter/web/app/dashboard/page.tsx`](./starter/web/app/dashboard/page.tsx#L259-L286))* |
| **Carpetas de Proyectos** | Tarjetas de carpeta con plataforma, fecha y estado | [`starter/web/components/projects/project-folder-card.tsx`](./starter/web/components/projects/project-folder-card.tsx) |
| **Carrusel Recomendado** | • Título: `Recomendado para ti`<br>• Enlace: `Ver todas las plantillas` | En [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L94-L95)<br>y [`starter/web/components/templates/template-carousel.tsx`](./starter/web/components/templates/template-carousel.tsx) |

---

## 📈 4. Tendencias (`/trends`)

| Sección / Elemento | Texto que ves en pantalla | Dónde se cambia el texto |
| :--- | :--- | :--- |
| **Cabecera de Tendencias** | • Eyebrow: `TENDENCIAS`<br>• Título: `Señales para tu próxima publicación`<br>• Subtítulo: `Explora tendencias observadas y verificables...`<br>• Botones: `Ver fuentes` y `Actualizar` | [`starter/web/lib/trends-copy.ts`](./starter/web/lib/trends-copy.ts#L4-L13)<br>*(Página: [`starter/web/app/trends/page.tsx`](./starter/web/app/trends/page.tsx#L138-L170))* |
| **Resumen de Señales** | `Señales visibles`, `Evidencias recopiladas`, `Fuentes activas`, `Última recopilación`, `Estado de las fuentes` | [`starter/web/lib/trends-copy.ts`](./starter/web/lib/trends-copy.ts#L47-L55) |
| **Tarjetas de Tendencia** | • Badges: `Reciente` / `Antigua`<br>• Métricas: `Score global`, `Relevancia para tu negocio`<br>• Botón: `Crear publicación` | [`starter/web/lib/trends-copy.ts`](./starter/web/lib/trends-copy.ts#L18-L25)<br>*(Página: [`starter/web/app/trends/page.tsx`](./starter/web/app/trends/page.tsx#L330-L417))* |

---

## 🎨 5. Plantillas Canva (`/templates`)

| Sección / Elemento | Texto que ves en pantalla | Dónde se cambia el texto |
| :--- | :--- | :--- |
| **Catálogo de Plantillas** | • Título: `Plantillas de Canva`<br>• Buscador: `Buscar plantillas por nombre o categoría...`<br>• Botón en tarjeta: `Abrir en Canva ↗` | [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L1250-L1275)<br>y [`starter/web/components/templates/template-library.tsx`](./starter/web/components/templates/template-library.tsx) |

---

## ⚙️ 6. Configuración y Ajustes (`/settings`)

| Pestaña | Texto que ves en pantalla | Dónde se cambia el texto |
| :--- | :--- | :--- |
| **Pestañas de Ajustes** | `Cuenta`, `Negocio`, `Voz de marca`, `Redes sociales`, `Idioma`, `Uso y límites`, `Privacidad`, `Eliminar cuenta` | [`starter/web/lib/i18n.ts`](./starter/web/lib/i18n.ts#L100-L110)<br>*(Página: [`starter/web/app/settings/page.tsx`](./starter/web/app/settings/page.tsx#L500-L520))* |
| **Cuenta** | Campos: `Nombre`, `Correo electrónico`, `Idioma de la interfaz`<br>• Botón: `Guardar cambios` | [`starter/web/app/settings/page.tsx`](./starter/web/app/settings/page.tsx#L532-L585) |
| **Negocio y Marca** | Campos: `Nombre de negocio`, `Categoría`, `Audiencia`, `Tonos de voz`, `Palabras preferidas`, `Color principal` | [`starter/web/app/settings/page.tsx`](./starter/web/app/settings/page.tsx#L587-L800) |
| **Redes Sociales** | Conectar cuentas de Instagram, TikTok, X | [`starter/web/components/settings/social-connections.tsx`](./starter/web/components/settings/social-connections.tsx) |

---

## 🚀 7. Onboarding / Cuestionario Inicial (`/onboarding`)

| Paso | Texto que ves en pantalla | Archivo del Componente |
| :--- | :--- | :--- |
| **Paso 1: Tu Negocio** | `Nombre del negocio`, `Categoría`, `País`, `Ciudad`, `Producto o servicio principal`, `Público objetivo` | [`starter/web/components/onboarding/step-business.tsx`](./starter/web/components/onboarding/step-business.tsx) |
| **Paso 2: Canales** | `¿En qué plataformas publicas?` (Instagram, TikTok, Facebook, etc.) y `Objetivo principal` | [`starter/web/components/onboarding/step-channels.tsx`](./starter/web/components/onboarding/step-channels.tsx) |
| **Paso 3: Marca y Tono** | `¿Cómo habla tu marca?` (Amigable, Profesional, Juvenil...) y `Colores de tu marca` | [`starter/web/components/onboarding/step-brand.tsx`](./starter/web/components/onboarding/step-brand.tsx) |
| **Paso 4: Revisión** | `Revisa los datos de tu negocio` y botón `Finalizar y empezar a crear` | [`starter/web/components/onboarding/step-review.tsx`](./starter/web/components/onboarding/step-review.tsx) |
