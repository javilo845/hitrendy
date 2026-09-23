import { expect, test, type Page } from "@playwright/test";

async function mockBetaApi(page: Page, authenticated = false) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path.endsWith("/auth/csrf")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ token: "e2e-csrf-token" }),
      });
      return;
    }
    if (path.endsWith("/auth/me")) {
      await route.fulfill({
        status: authenticated ? 200 : 401,
        contentType: "application/json",
        body: JSON.stringify(
          authenticated
            ? {
                user: {
                  id: "user-beta",
                  name: "Tester Beta",
                  email: "tester@example.com",
                },
                workspaces: [{ id: "workspace-beta", role: "owner" }],
              }
            : { error: { code: "UNAUTHENTICATED", message: "Sesión requerida" } },
        ),
      });
      return;
    }
    if (path.endsWith("/auth/signup") && method === "GET") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "SIGNUP_NOT_FOUND" } }),
      });
      return;
    }
    if (path.endsWith("/auth/password-reset/request")) {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          message: "Si existe una cuenta con ese correo, recibirás instrucciones.",
        }),
      });
      return;
    }
    if (path.endsWith("/policies")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          privacy: { version: "2026-08-02", path: "/privacy", retention_days: 365 },
          terms: { version: "2026-08-02", path: "/terms" },
          support: { email: "beta-support@example.com", path: "/feedback" },
          email_verification: "disabled",
          closed_beta: false,
        }),
      });
      return;
    }
    if (path.endsWith("/feedback") && method === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "feedback-beta", status: "open" }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test("las políticas de beta están disponibles", async ({ page }) => {
  await mockBetaApi(page);
  await page.goto("/privacy");
  await expect(page.getByRole("heading", { name: "Privacidad" })).toBeVisible();
  await expect(page.getByRole("link", { name: "beta-support@example.com" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Leer términos" })).toBeVisible();

  await page.goto("/terms");
  await expect(
    page.getByRole("heading", { name: "Términos de la beta cerrada" }),
  ).toBeVisible();
});

test("recuperación y registro muestran el camino de beta", async ({ page }) => {
  await mockBetaApi(page);
  await page.goto("/reset-password");
  await expect(page.getByRole("heading", { name: "Recupera tu acceso" })).toBeVisible();
  await page.getByLabel("Correo electrónico").fill("tester@example.com");
  await page.getByRole("button", { name: "Enviar instrucciones" }).click();
  await expect(page.getByRole("status")).toContainText("recibirás instrucciones");

  await page.goto("/register");
  await expect(page.getByLabel(/Código de invitación/)).toBeVisible();
});

test("el soporte de beta requiere sesión y permite enviar feedback", async ({ page }) => {
  await mockBetaApi(page, true);
  await page.goto("/feedback");
  await expect(page.getByRole("heading", { name: "¿Cómo podemos mejorar?" })).toBeVisible();
  await page.getByRole("textbox", { name: "Mensaje" }).fill("El flujo de beta fue claro.");
  await page.getByRole("button", { name: "Enviar feedback" }).click();
  await expect(page.getByRole("status")).toContainText("Recibimos tu mensaje");
});
