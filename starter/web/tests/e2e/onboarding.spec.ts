import { expect, test, type Page } from "@playwright/test";

type SignupDraft = Record<string, unknown>;

function pendingResponse(draft: SignupDraft, version: number) {
  const current_step = draft.review
    ? "review"
    : draft.brand
      ? "review"
      : draft.channels
        ? "brand"
        : draft.business
          ? "channels"
          : "business";
  return {
    signup: {
      status: "pending",
      current_step,
      expires_at: "2099-01-01T00:00:00+00:00",
      updated_at: "2099-01-01T00:00:00+00:00",
      version,
      draft,
    },
  };
}

async function mockSignupFlow(page: Page, authenticatedAtStart = false) {
  let pending = false;
  let authenticated = authenticatedAtStart;
  let version = 1;
  let draft: SignupDraft = {};
  let completeRequests = 0;
  const completionKeys: string[] = [];
  const savedPayloads: SignupDraft[] = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path.endsWith("/auth/me")) {
      if (authenticated) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            user: { id: "user-1", name: "Ana", email: "ana@example.com" },
            workspaces: [{ id: "workspace-1", role: "owner" }],
          }),
        });
      } else {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({
            error: { code: "UNAUTHENTICATED", message: "Sesión requerida" },
          }),
        });
      }
      return;
    }

    if (path.endsWith("/trends/home")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "empty",
          refresh_scope: { region: "HN", category: null },
          updated_at: null,
          refresh_allowed: false,
          next_refresh_at: null,
          sources: {
            total: 0,
            available: 0,
            degraded: 0,
            quota_exhausted: 0,
            unavailable: 0,
            unconfigured: 0,
            disabled: 0,
          },
          items: [],
        }),
      });
      return;
    }

    if (path.endsWith("/auth/signup/start") && method === "POST") {
      pending = true;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(pendingResponse(draft, version)),
      });
      return;
    }

    if (path.endsWith("/auth/signup") && method === "GET") {
      if (!pending) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "SIGNUP_NOT_FOUND",
              message: "No hay registro pendiente.",
            },
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(pendingResponse(draft, version)),
        });
      }
      return;
    }

    if (path.endsWith("/auth/signup") && method === "PATCH") {
      const payload = request.postDataJSON() as SignupDraft & {
        expected_version: number;
        step: string;
      };
      version += 1;
      draft = { ...draft, [payload.step]: payload[payload.step] };
      savedPayloads.push(payload);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(pendingResponse(draft, version)),
      });
      return;
    }

    if (path.endsWith("/auth/signup/complete") && method === "POST") {
      completeRequests += 1;
      completionKeys.push(request.headers()["idempotency-key"] || "");
      if (completeRequests === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            error: { code: "TEMPORARY", message: "Temporal", retryable: true },
          }),
        });
        return;
      }
      pending = false;
      authenticated = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: { id: "user-1", name: "Ana", email: "ana@example.com" },
          workspace: { id: "workspace-1", role: "owner" },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  return {
    get completeRequests() {
      return completeRequests;
    },
    completionKeys,
    savedPayloads,
  };
}

test("registro, draft servidor y finalización llevan al dashboard", async ({
  page,
}) => {
  const state = await mockSignupFlow(page);
  await page.goto("/register");

  await page.getByLabel("Tu nombre").fill("Ana Registro");
  await page.getByLabel("Correo electrónico").fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("una-clave-segura-123");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(
    page.getByRole("heading", { name: "Cuéntanos sobre tu negocio" })
  ).toBeVisible();

  await page.getByLabel(/Nombre comercial/).fill("Café Central");
  await page.getByLabel(/Categoría/).selectOption("gastronomy");
  await page.getByLabel(/País/).fill("Honduras");
  await page.getByLabel(/Ciudad/).fill("Tegucigalpa");
  await page.getByLabel(/Producto o servicio principal/).fill("Café artesanal");
  await page.getByLabel(/¿A quién ayudas/).fill("Personas que trabajan cerca");
  await page.getByRole("button", { name: "Siguiente" }).click();
  await expect(
    page.getByRole("heading", { name: "Canales y objetivos" })
  ).toBeVisible();

  await page.getByLabel("Instagram").check();
  await page.getByLabel("Objetivo principal *").selectOption("sales");
  await page.getByRole("button", { name: "Siguiente" }).click();
  await expect(
    page.getByRole("heading", { name: "Identidad de marca" })
  ).toBeVisible();

  await page.getByLabel("Cercano").check();
  await page
    .getByLabel(/Propuesta de valor/)
    .fill("Café artesanal para tu día");
  await page.getByRole("button", { name: "Siguiente" }).click();
  await expect(
    page.getByRole("heading", { name: "Revisa tu información" })
  ).toBeVisible();

  await page.getByLabel(/Confirmo que la información/).check();
  await page
    .getByRole("button", { name: "Finalizar y entrar a HiTrendy" })
    .click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("heading", { name: "Señales para tu próxima publicación" })
  ).toBeVisible();
  expect(state.savedPayloads).toHaveLength(4);
  expect(state.completeRequests).toBe(2);
  expect(state.completionKeys[0]).toBeTruthy();
  expect(state.completionKeys[1]).toBe(state.completionKeys[0]);
});

test("las guardas separan visitante, pending signup y usuario activo", async ({
  page,
}) => {
  const state = await mockSignupFlow(page);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);

  await page.goto("/register");
  await page.getByLabel("Tu nombre").fill("Ana Registro");
  await page.getByLabel("Correo electrónico").fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("una-clave-segura-123");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/onboarding$/);

  await page.goto("/onboarding");
  await expect(page).toHaveURL(/\/onboarding$/);
  expect(state.completeRequests).toBe(0);
});

test("un usuario activo no vuelve a entrar al onboarding", async ({ page }) => {
  await mockSignupFlow(page, true);
  await page.goto("/onboarding");
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("un pending signup expirado vuelve al registro", async ({ page }) => {
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "UNAUTHENTICATED" } }),
    });
  });
  await page.route("**/api/v1/auth/signup**", async (route) => {
    await route.fulfill({
      status: 410,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "SIGNUP_EXPIRED",
          message: "El registro pendiente expiró.",
        },
      }),
    });
  });
  await page.goto("/onboarding");
  await expect(page).toHaveURL(/\/register$/);
});
