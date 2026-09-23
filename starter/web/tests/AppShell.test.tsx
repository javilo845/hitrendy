import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { AppShell } from "@/components/shell/app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/studio/new",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/components/auth/protected-route", () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

describe("AppShell", () => {
  test("marks the active route and keeps navigation names available", () => {
    render(
      <AppShell>
        <p>Contenido de prueba</p>
      </AppShell>
    );

    expect(screen.getAllByRole("link", { name: "Studio" })[0]).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(screen.getAllByRole("link", { name: "Dashboard" })[0]).toHaveAttribute(
      "href",
      "/dashboard"
    );
    expect(screen.getAllByRole("link", { name: "Tendencias" })[0]).toHaveAttribute(
      "href",
      "/trends"
    );
    expect(
      screen.getByRole("complementary", { name: "Navegación principal" })
    ).toBeInTheDocument();
    expect(screen.getByText("Contenido de prueba")).toBeInTheDocument();
  });
});
