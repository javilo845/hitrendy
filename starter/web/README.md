# HiTrendy web

Frontend Next.js/TypeScript integrado con el backend real del repositorio.

## Desarrollo

Desde la raíz del monorepo:

```bash
npm ci
npm run dev -w starter/web
```

Validaciones del frontend:

```bash
npm run typecheck -w starter/web
npm run lint -w starter/web
npm run test -w starter/web
npm run build -w starter/web
```

El alta pública usa siempre el backend real:

1. `/register` inicia un Pending Signup.
2. `/onboarding` recupera y guarda el borrador con la cookie temporal del
   backend.
3. La confirmación llama a `/api/v1/auth/signup/complete` con una clave
   idempotente estable y solo después dirige al dashboard.

El demo local ya no tiene una entrada pública ni puede saltarse autenticación.
Los helpers fake permanecen disponibles únicamente para pruebas o para un
entorno local explícito con `NEXT_PUBLIC_ENABLE_DEMO=true`; esa bandera no se
activa en producción.

Cuando el backend tiene Google configurado, las pantallas de registro e inicio
de sesión muestran **Continuar con Google**. El navegador recibe únicamente la
URL de autorización generada por el backend; el callback vuelve al onboarding
para una cuenta nueva o al dashboard para una identidad ya vinculada.

La configuración (`/settings`) sigue siendo la implementación existente del
repositorio. Las rutas antiguas (`/assistant`, `/conversations`, `/projects`)
se mantienen como alias de compatibilidad hacia el App Shell actual.

El análisis de tendencias en tiempo real no forma parte del MVP actual. La
prioridad de esta entrega es generar, editar y guardar contenido, dejando el
contexto de tendencias para una fase posterior con fuentes autorizadas.
