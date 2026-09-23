import { expect, test, type Page } from "@playwright/test";

async function mockAnonymousGoogleStatus(page: Page, configured: boolean) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "UNAUTHENTICATED" } }),
      });
      return;
    }
    if (path.endsWith("/auth/signup")) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "SIGNUP_NOT_FOUND" } }),
      });
      return;
    }
    if (path.endsWith("/auth/google/status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ configured }),
      });
      return;
    }
    if (path.endsWith("/auth/google/start")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authorization_url: `${new URL(request.url()).origin}/oauth-provider` }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
}

test("login inicia el redirect Google generado por backend", async ({ page }) => {
  await mockAnonymousGoogleStatus(page, true);
  await page.goto("/login");
  const button = await page.getByRole("button", { name: "Continuar con Google" });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page).toHaveURL(/\/oauth-provider$/);
});

test("registro muestra Google como no disponible sin simular OAuth", async ({ page }) => {
  await mockAnonymousGoogleStatus(page, false);
  await page.goto("/register");
  await expect(page.getByRole("button", { name: "Continuar con Google" })).toBeDisabled();
  await expect(page.getByText("Google no está disponible en este momento.")).toBeVisible();
});

test("login muestra un error seguro devuelto por el callback", async ({ page }) => {
  await mockAnonymousGoogleStatus(page, true);
  await page.goto("/login?oauth=failed");
  await expect(
    page.getByText("No pudimos completar el acceso con Google. Inténtalo de nuevo.")
  ).toBeVisible();
});
