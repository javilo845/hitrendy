import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, test, vi } from "vitest";

import TrendsPage from "@/app/trends/page";
import { api } from "@/lib/api";
import type { TrendHome, TrendHomeStatus, TrendSource } from "@/types/trends";

vi.mock("@/components/shell/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const evidence = {
  source: "rss-local",
  source_name: "Noticias locales",
  source_url: "https://example.test/evidence",
  observed_at: "2026-07-30T10:00:00Z",
};

const otherScopeEvidence = {
  source: "rss-global",
  source_name: "Noticias globales",
  source_url: "https://example.test/evidence-global",
  observed_at: "2026-07-29T10:00:00Z",
};

function home(status: TrendHomeStatus = "fresh"): TrendHome {
  return {
    status,
    // Only the scope the refresh button collects: the cards below are
    // aggregated and each one declares its own region/category.
    refresh_scope: { region: "HN", category: "gastronomy" },
    updated_at: "2026-07-30T12:00:00Z",
    refresh_allowed: true,
    next_refresh_at: null,
    sources: {
      total: 1,
      available: 1,
      degraded: 0,
      quota_exhausted: 0,
      unavailable: 0,
      unconfigured: 0,
      disabled: 0,
    },
    items:
      status === "empty" || status === "disabled" || status === "unconfigured"
        ? []
        : [
            {
              id: "trend-visible-1",
              title: "Café frío local",
              summary: "Una señal observada con evidencia pública.",
              region: "HN",
              category: "gastronomy",
              observed_at: "2026-07-30T10:00:00Z",
              freshness: status === "stale" ? "stale" : "fresh",
              freshness_score: 0.9,
              total_score: 0.82,
              workspace_relevance: {
                score: 0.75,
                calculated_at: "2026-07-30T12:00:00Z",
              },
              evidence: [evidence],
            },
            {
              id: "trend-visible-2",
              title: "Empaque reutilizable",
              summary: "Una señal observada en otro alcance.",
              region: "GLOBAL",
              category: "retail",
              observed_at: "2026-07-29T10:00:00Z",
              freshness: status === "stale" ? "stale" : "fresh",
              freshness_score: 0.6,
              total_score: 0.71,
              workspace_relevance: {
                score: 0.4,
                calculated_at: "2026-07-30T12:00:00Z",
              },
              evidence: [otherScopeEvidence],
            },
          ],
  };
}

const source: TrendSource = {
  identifier: "rss-local",
  public_name: "Noticias locales",
  source_type: "rss",
  configured: true,
  status: "available",
  next_reset_at: null,
};

beforeEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("Trends Home", () => {
  test("renders verifiable cards, visible dates, CTA by ID and basic accessibility", async () => {
    vi.spyOn(api.trends, "home").mockResolvedValue(home());
    const { container } = render(<TrendsPage />);

    expect(await screen.findByRole("heading", { name: "Café frío local" })).toBeInTheDocument();
    // Card date, evidence date, and the collection overview at the top.
    expect(screen.getAllByText(/30 jul 2026/i)).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Noticias locales" })).toHaveAttribute(
      "href",
      evidence.source_url
    );
    // The CTA is scoped per card because Home aggregates several scopes.
    const [firstCard] = screen.getAllByRole("article");
    expect(within(firstCard).getByRole("link", { name: "Crear publicación" })).toHaveAttribute(
      "href",
      "/studio/new?trend=trend-visible-1"
    );
    const results = await axe(container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  test("shows loading skeleton and recoverable error", async () => {
    let rejectLoad: (reason: Error) => void = () => undefined;
    vi.spyOn(api.trends, "home").mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectLoad = reject;
        })
    );
    render(<TrendsPage />);
    expect(screen.getByLabelText("Cargando tendencias")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    rejectLoad(new Error("offline"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No pudimos cargar las tendencias."
    );
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  test.each([
    ["empty", "No encontramos tendencias nuevas"],
    ["stale", "Estas señales son antiguas"],
    ["disabled", "El análisis de tendencias está desactivado"],
    ["unconfigured", "Todavía no hay fuentes"],
    ["degraded", "Algunas fuentes tuvieron problemas"],
    ["failed", "La última recopilación no pudo completarse"],
  ] as const)("renders the %s state", async (status, label) => {
    vi.spyOn(api.trends, "home").mockResolvedValue(home(status));
    render(<TrendsPage />);
    expect(await screen.findByText(new RegExp(label, "i"))).toBeInTheDocument();
  });

  test("keeps the collection visible when there are no signals", async () => {
    const empty = {
      ...home("empty"),
      sources: {
        total: 3,
        available: 1,
        degraded: 1,
        quota_exhausted: 0,
        unavailable: 1,
        unconfigured: 0,
        disabled: 0,
      },
    };
    vi.spyOn(api.trends, "home").mockResolvedValue(empty);
    const { container } = render(<TrendsPage />);

    // The overview counts what the API returned; it never fills the gap with
    // an invented figure.
    expect(
      await screen.findByText("Todavía no hay señales que mostrar")
    ).toBeInTheDocument();
    const signals = screen.getByText("Señales visibles").parentElement!;
    expect(within(signals).getByText("0")).toBeInTheDocument();
    const active = screen.getByText("Fuentes activas").parentElement!;
    expect(active.textContent).toContain("1");
    expect(active.textContent).toContain("/3");
    expect(screen.getByText("Estado de las fuentes")).toBeInTheDocument();
    expect(screen.getByText("Degradada")).toBeInTheDocument();
    expect(screen.getByText("No disponible")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Abrir el Studio" })
    ).toHaveAttribute("href", "/studio/new");

    const results = await axe(container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  test("shows cooldown and does not offer refresh before its deadline", async () => {
    const cooldown = {
      ...home(),
      refresh_allowed: false,
      next_refresh_at: "2026-07-31T00:00:00Z",
    };
    vi.spyOn(api.trends, "home").mockResolvedValue(cooldown);
    const refresh = vi.spyOn(api.trends, "refresh");
    render(<TrendsPage />);
    const button = await screen.findByRole("button", { name: "Actualizar" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByText(/Próxima actualización disponible/)).toBeInTheDocument();
  });

  test("refreshes explicitly and reloads Home", async () => {
    const first = home();
    const cooled = {
      ...first,
      refresh_allowed: false,
      next_refresh_at: "2026-07-31T00:00:00Z",
    };
    vi.spyOn(api.trends, "home")
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(cooled);
    vi.spyOn(api.trends, "refresh").mockResolvedValue({
      id: "run-1",
      status: "completed",
      refresh_allowed: false,
      next_refresh_at: cooled.next_refresh_at,
      retry_after_seconds: 3600,
    });
    render(<TrendsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Actualizar" }));
    await waitFor(() =>
      expect(api.trends.refresh).toHaveBeenCalledWith(
        first.refresh_scope,
        expect.objectContaining({ idempotencyKey: expect.any(String) })
      )
    );
    expect(api.trends.refresh).toHaveBeenCalledWith(
      { region: "HN", category: "gastronomy" },
      expect.anything()
    );
    expect(await screen.findByText(/Próxima actualización disponible/)).toBeInTheDocument();
  });

  test("aggregates every scope and only claims the refresh scope", async () => {
    const aggregated = home();
    vi.spyOn(api.trends, "home").mockResolvedValue(aggregated);
    render(<TrendsPage />);

    // Cards from both scopes are visible, each declaring its own scope.
    const cards = within(
      await screen.findByRole("region", { name: "Señales para tu próxima publicación" })
    ).getAllByRole("article");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText("HN · Gastronomía")).toBeInTheDocument();
    expect(within(cards[1]).getByText("GLOBAL · Comercio")).toBeInTheDocument();
    expect(
      within(cards[1]).getByRole("heading", { name: "Empaque reutilizable" })
    ).toBeInTheDocument();

    // The header never claims the cards belong to the button scope: it only
    // labels what the button will collect.
    const scopeNote = screen.getByText("El botón actualiza solo el alcance").parentElement;
    expect(scopeNote).toHaveTextContent("HN · Gastronomía");
    expect(scopeNote).not.toHaveTextContent("GLOBAL");
  });

  test("loads the safe sources modal and closes it from the keyboard", async () => {
    vi.spyOn(api.trends, "home").mockResolvedValue(home());
    vi.spyOn(api.trends, "sources").mockResolvedValue([source]);
    render(<TrendsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Ver fuentes/ }));
    const dialog = await screen.findByRole("dialog", { name: "Fuentes de tendencias" });
    expect(within(dialog).getByText("Noticias locales")).toBeInTheDocument();
    expect(within(dialog).getByText("Disponible")).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
