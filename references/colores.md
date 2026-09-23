# Paleta de colores — HiTrendy

Colores usados en `index.html` (landing, quiénes somos, login y pantalla principal).

## Tokens

| Variable | Hex | Uso |
|---|---|---|
| `--navy` | `#1E1A5E` | Fondo del hero y de la sección "¿Quiénes somos?" |
| `--navy-deep` | `#141043` | Sombras y fondos de apoyo |
| `--ink` | `#12103A` | Botón "Comenzar", botón "Iniciar sesión", texto oscuro |
| `--purple` | `#7C3AED` | Logo, acentos, anillo de foco |
| `--purple-light` | `#A78BFA` | Degradados y garabatos decorativos |
| `--purple-soft` | `#C4A6F7` | Fondo de la pantalla de login |
| `--pink` | `#F472E0` | Título "¿Quiénes somos?" |
| `--white` | `#FFFFFF` | Navbar, tarjetas, texto sobre fondo oscuro |
| `--paper` | `#F6F4FF` | Formulario de login y pantalla principal |
| `--muted` | `#8B87B8` | Labels y texto secundario |

## CSS

```css
:root{
  --navy:#1E1A5E;
  --navy-deep:#141043;
  --ink:#12103A;
  --purple:#7C3AED;
  --purple-light:#A78BFA;
  --purple-soft:#C4A6F7;
  --pink:#F472E0;
  --white:#FFFFFF;
  --paper:#F6F4FF;
  --muted:#8B87B8;
}
```

## Degradados

Van inline en el CSS, no son variables.

| Dónde | Valor |
|---|---|
| Logo "HiTrendy" | `linear-gradient(92deg, #6D28D9, #A855F7)` |
| Título "¿Quiénes somos?" | `linear-gradient(96deg, #F9A8F0, #C79BFF 60%, #A78BFA)` |
| Fondo del login | `linear-gradient(160deg, #C9AEF9, #B79BF5 45%, #A98BF2)` |
| Panel morado del login | `linear-gradient(200deg, #3C2C9A, #6D45D6 55%, #A98BF2)` |
| Botón de Google | `linear-gradient(92deg, #7C3AED, #A855F7)` |
| Brillo del hero | `radial-gradient(120% 90% at 50% -10%, #2B2478, transparent 60%)` |

## Detalles del formulario

| Elemento | Hex |
|---|---|
| Divisor "o con tu correo" | `#DED8F2` |
| Línea inferior de los inputs | `#D9D2F0` |
| Enlace "¿Olvidaste tu contraseña?" | `#C0399B` |
| Título "¡Bienvenido de vuelta!" | `#2A1170` |
| Texto de "Recordarme" | `#514B7A` |
| Mensaje de error | `#C81E5B` |
| Borde de las tarjetas de la principal | `#E9E3FB` |
| Fondo del avatar y de los iconos | `#EDE7FE` |

## Decorativos

Colores de relleno de los posters del hero y del collage. Son provisionales: bórralos cuando entren las imágenes reales.

| Elemento | Colores |
|---|---|
| Poster 1 — "Nuevo sabor" | `#2F7FD6` → `#7EC4F2` → `#E7F4FF` |
| Poster 2 — "Summer is ending" | `#1B7FD8` → `#63C0F0` → `#B9E4FF` |
| Poster 3 — floristería | `#FDF3F6` → `#F3D3DE`, flor `#F9B8CE` / `#E8749E` / `#C64B7E` |
| Poster 4 — panadería "junio" | `#E9D9CB` → `#C9A98E` → `#8E6A4E` |
| Poster 5 — cafetería | `#0F3FA8` → `#1E63D6` → `#0B2E86`, amarillo `#FFD84D` |
| Collage — tile principal | `#E9822F` → `#F2B65A` → `#7FC7E8`, matcha `#E7F3C0` / `#8FBF4D` |
| Collage — tiles secundarios | `#D94B2B`, `#F0A24A`, `#1D4FD8`, `#F5C542`, `#CBB9FF` |
| Corazón de la píldora "Love it!" | `#FF4D8D` |
| Garabatos morados | `#A855F7`, `#5B3BC4`, `#4C2FA8` |
