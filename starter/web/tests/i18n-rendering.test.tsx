import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { api } from "@/lib/api";
import { DELETION_TOKEN_KEY } from "@/lib/deletion-status";
import { LOCALE_STORAGE_KEY, type AppLocale } from "@/lib/i18n";

vi.mock("next/navigation", () => ({
  usePathname: () => "/account-deletion-status",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/auth/protected-route", () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

vi.mock("@/components/auth/public-auth-route", () => ({
  PublicAuthRoute: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

vi.mock("@/components/auth/signup-route", () => ({
  SignupRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const EXPECTED_PROCESSING: Record<AppLocale, string> = {
  es: "En proceso. Estamos eliminando tus datos.",
  en: "In progress. We are deleting your data.",
  pt: "Em andamento. Estamos excluindo seus dados.",
};

const EXPECTED_TITLE: Record<AppLocale, string> = {
  es: "Estado de la eliminación",
  en: "Deletion status",
  pt: "Status da exclusão",
};

const EXPECTED_NAV_STUDIO: Record<AppLocale, string> = {
  es: "Studio",
  en: "Studio",
  pt: "Studio",
};

const EXPECTED_NAV_SETTINGS: Record<AppLocale, string> = {
  es: "Configuración",
  en: "Settings",
  pt: "Configurações",
};

const EXPECTED_NAV_DASHBOARD: Record<AppLocale, string> = {
  es: "Dashboard",
  en: "Dashboard",
  pt: "Dashboard",
};

const EXPECTED_NAV_TRENDS: Record<AppLocale, string> = {
  es: "Tendencias",
  en: "Trends",
  pt: "Tendências",
};

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("account-deletion-status page renders real copy per locale", () => {
  for (const locale of ["es", "en", "pt"] as const) {
    test(`shows the ${locale} title and processing state text`, async () => {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      window.sessionStorage.setItem(DELETION_TOKEN_KEY, "a".repeat(43));
      vi.spyOn(api.auth, "deletionStatus").mockResolvedValue({
        status: "processing",
      });

      const { default: AccountDeletionStatusPage } =
        await import("@/app/account-deletion-status/page");
      render(<AccountDeletionStatusPage />);

      expect(
        await screen.findByText(EXPECTED_PROCESSING[locale])
      ).toBeInTheDocument();
      expect(screen.getByText(EXPECTED_TITLE[locale])).toBeInTheDocument();
    });
  }
});

describe("primary navigation renders real copy per locale", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", globalThis.crypto);
  });

  for (const locale of ["es", "en", "pt"] as const) {
    test(`shows navigation labels in ${locale}`, async () => {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);

      const { AppShell } = await import("@/components/shell/app-shell");
      render(
        <AppShell>
          <p>content</p>
        </AppShell>
      );

      expect(
        screen.getAllByText(EXPECTED_NAV_STUDIO[locale])[0]
      ).toBeInTheDocument();
      expect(
        screen.getAllByText(EXPECTED_NAV_SETTINGS[locale])[0]
      ).toBeInTheDocument();
      expect(
        screen.getAllByText(EXPECTED_NAV_DASHBOARD[locale])[0]
      ).toBeInTheDocument();
      expect(
        screen.getAllByText(EXPECTED_NAV_TRENDS[locale])[0]
      ).toBeInTheDocument();
    });
  }
});

describe("authentication surfaces render catalog copy", () => {
  const loginHeadings: Record<AppLocale, string> = {
    es: "¡Bienvenido de vuelta!",
    en: "Welcome back",
    pt: "Boas-vindas de volta",
  };
  const registerHeadings: Record<AppLocale, string> = {
    es: "Crea tu cuenta",
    en: "Create your account",
    pt: "Crie sua conta",
  };

  for (const locale of ["es", "en", "pt"] as const) {
    test(`login and registration render ${locale} rather than catalog keys`, async () => {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      const { default: LoginPage } = await import("@/app/login/page");
      const { default: RegisterPage } = await import("@/app/register/page");
      const login = render(<LoginPage />);
      expect(
        await screen.findByRole("heading", { name: loginHeadings[locale] })
      ).toBeInTheDocument();
      expect(screen.queryByText("auth.welcome")).not.toBeInTheDocument();
      login.unmount();
      render(<RegisterPage />);
      expect(
        await screen.findByRole("heading", { name: registerHeadings[locale] })
      ).toBeInTheDocument();
      expect(screen.queryByText("auth.register")).not.toBeInTheDocument();
    });
  }

  test("registration changes the cached locale dynamically", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "es");
    const { default: RegisterPage } = await import("@/app/register/page");
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Idioma de la interfaz"), {
      target: { value: "en" },
    });
    expect(
      await screen.findByRole("heading", { name: "Create your account" })
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en");
  });
});

describe("template surface uses the common catalog", () => {
  test("uses the stored Portuguese locale and preserves template titles", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "pt");
    vi.spyOn(api.templates, "list").mockResolvedValue([
      {
        id: "template-user-id",
        title: "Marca do usuário",
        platforms: ["instagram"],
        formats: ["static_post"],
        category: "other",
        thumbnail_url: "/missing.png",
        editable_slots: [],
        aspect_ratio: "4:5",
      },
    ] as never);
    const { default: TemplatesPage } = await import("@/app/templates/page");
    render(<TemplatesPage />);
    expect(
      await screen.findByRole("heading", { name: "Explore templates" })
    ).toBeInTheDocument();
    expect(screen.getByText("Marca do usuário")).toBeInTheDocument();
    expect(screen.queryByText("templates.title")).not.toBeInTheDocument();
  });
});

describe("remaining primary surfaces use persisted interface copy", () => {
  test("settings loads its persisted English locale and trends renders trend copy", async () => {
    vi.spyOn(api.auth, "me").mockResolvedValue({
      user: {
        id: "u",
        name: "Ana",
        email: "ana@example.test",
        interface_locale: "en",
      },
    } as never);
    vi.spyOn(api.auth, "usage").mockResolvedValue({ items: [] } as never);
    vi.spyOn(api.businesses, "list").mockResolvedValue([] as never);
    const { default: SettingsPage } = await import("@/app/settings/page");
    render(<SettingsPage />);
    expect(
      await screen.findByRole("heading", { name: "Settings" })
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en");

    vi.spyOn(api.trends, "home").mockResolvedValue({
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
    });
    const { default: TrendsPage } = await import("@/app/trends/page");
    render(<TrendsPage />);
    expect(
      await screen.findByRole("heading", { name: "Signals for your next post" })
    ).toBeInTheDocument();
    expect(
      screen.getByText("No new trends were found for this scope.")
    ).toBeInTheDocument();
  });

  test("onboarding business and channels steps render Portuguese labels", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "pt");
    const { StepBusiness } =
      await import("@/components/onboarding/step-business");
    const { StepChannels } =
      await import("@/components/onboarding/step-channels");
    const business = render(
      <StepBusiness
        data={{
          name: "",
          category: "",
          country: "",
          city: "",
          description: "",
          primary_product: "",
          target_audience: "",
          website_url: "",
        }}
        onChange={vi.fn()}
      />
    );
    expect(
      screen.getByRole("heading", { name: "Conte-nos sobre seu negócio" })
    ).toBeInTheDocument();
    business.unmount();
    render(
      <StepChannels
        data={{ preferred_platforms: [], primary_objective: "" }}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByText("Canais e objetivos")).toBeInTheDocument();
  });
});
