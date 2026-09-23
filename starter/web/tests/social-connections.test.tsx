import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import SettingsPage from "@/app/settings/page";
import {
  SocialConnections,
  type SocialCallbackNotice,
} from "@/components/settings/social-connections";
import { api, resetCsrfToken } from "@/lib/api";
import type {
  SocialConnection,
  SocialConnectionsResponse,
  SocialProviderDescriptor,
  SocialProviderName,
} from "@/types/social";

const navigation = vi.hoisted(() => ({
  query: "",
  pathname: "/settings",
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ replace: navigation.replace, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

vi.mock("@/components/shell/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const fetchMock = vi.fn<
  [input: RequestInfo | URL, init?: RequestInit],
  Promise<Response>
>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function provider(
  name: SocialProviderName,
  status: SocialProviderDescriptor["status"] = "available",
  reason_code: SocialProviderDescriptor["reason_code"] = null
): SocialProviderDescriptor {
  return { name, status, reason_code };
}

function response(
  connections: SocialConnection[] = [],
  providers: SocialProviderDescriptor[] = [provider("demo")]
): SocialConnectionsResponse {
  return { enabled: true, providers, connections };
}

function connection(
  overrides: Partial<SocialConnection> = {}
): SocialConnection {
  return {
    id: "connection-1",
    provider: "demo",
    display_name: "Cuenta demo",
    account_type: "business",
    status: "connected",
    connected_at: "2026-08-01T12:00:00Z",
    last_checked_at: "2026-08-01T13:00:00Z",
    safe_error: null,
    ...overrides,
  };
}

function providerItem(name: string): HTMLElement {
  const heading = screen.getByRole("heading", { name });
  const item = heading.closest("li");
  if (!item) throw new Error(`Provider item missing for ${name}`);
  return item;
}

function configureSettingsPage() {
  vi.spyOn(api.auth, "me").mockResolvedValue({
    user: {
      id: "user-1",
      name: "Ana",
      email: "ana@example.test",
      interface_locale: "es",
      deletion_confirmation_phrase: "ELIMINAR",
    },
    workspaces: [],
  });
  vi.spyOn(api.businesses, "list").mockResolvedValue([]);
  vi.spyOn(api.auth, "usage").mockResolvedValue({ period_days: 30, items: [] });
}

beforeEach(() => {
  navigation.query = "";
  navigation.replace.mockReset();
  resetCsrfToken();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("SocialConnections", () => {
  test("renders a connected account, type, status and localized dates", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(response([connection()])));

    render(<SocialConnections locale="es" />);

    expect(
      await screen.findByRole("heading", { name: "Cuenta demo" })
    ).toBeInTheDocument();
    expect(screen.getByText("Empresa")).toBeInTheDocument();
    expect(screen.getByText("Conectada")).toBeInTheDocument();
    expect(screen.getAllByText(/2026/)).toHaveLength(2);
  });

  test.each([
    ["expired", "Expirada"],
    ["revoked", "Revocada"],
    ["degraded", "Degradada"],
  ] as const)("renders the %s status label", async (status, label) => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(response([connection({ status })]))
    );

    render(<SocialConnections locale="es" />);

    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  test("renders an error status and its translated safe error", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        response([connection({ status: "error", safe_error: "token_expired" })])
      )
    );

    render(<SocialConnections locale="es" />);

    expect(await screen.findByText("Con error")).toBeInTheDocument();
    expect(screen.getByText("Credencial expirada")).toBeInTheDocument();
  });

  test("disables an unconfigured provider and explains its reason", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        response([], [provider("instagram", "unconfigured", "not_configured")])
      )
    );

    render(<SocialConnections locale="es" />);

    await screen.findByRole("heading", { name: "Instagram" });
    const item = providerItem("Instagram");
    expect(
      within(item).getByRole("button", { name: "Conectar" })
    ).toBeDisabled();
    expect(within(item).getByText("Sin configurar")).toBeInTheDocument();
    expect(
      within(item).getByText("Este proveedor no está configurado.")
    ).toBeInTheDocument();
  });

  test("disables a disabled provider and explains its reason", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        response([], [provider("tiktok", "disabled", "requires_paid_plan")])
      )
    );

    render(<SocialConnections locale="es" />);

    await screen.findByRole("heading", { name: "TikTok" });
    const item = providerItem("TikTok");
    expect(
      within(item).getByRole("button", { name: "Conectar" })
    ).toBeDisabled();
    expect(within(item).getByText("Desactivado")).toBeInTheDocument();
    expect(
      within(item).getByText("Requiere un plan de pago.")
    ).toBeInTheDocument();
  });

  test("renders loading, empty and load-error states distinctly", async () => {
    let resolvePending: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      resolvePending = resolve;
    });
    fetchMock.mockReturnValueOnce(pending);

    const loadingView = render(<SocialConnections locale="es" />);
    expect(
      screen.getByText("Cargando conexiones sociales…")
    ).toBeInTheDocument();
    resolvePending(jsonResponse(response()));
    await screen.findByText("Aún no hay cuentas sociales conectadas.");
    loadingView.unmount();

    fetchMock.mockResolvedValueOnce(jsonResponse(response()));
    const emptyView = render(<SocialConnections locale="es" />);
    expect(
      await screen.findByText("Aún no hay cuentas sociales conectadas.")
    ).toBeInTheDocument();
    emptyView.unmount();

    fetchMock.mockRejectedValueOnce(new Error("network"));
    render(<SocialConnections locale="es" />);
    expect(
      await screen.findByText("No pudimos cargar las conexiones sociales.")
    ).toBeInTheDocument();
  });

  test("connects through authorize and navigates to its returned URL", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response()))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockResolvedValueOnce(
        jsonResponse({
          provider: "demo",
          authorization_url: "https://provider.example/authorize?state=opaque",
        })
      );
    const assign = vi.fn<[url: string | URL], void>();

    render(
      <SocialConnections
        locale="es"
        navigateToAuthorization={(url) => assign(url)}
      />
    );
    await screen.findByRole("heading", { name: "Demo" });
    const item = providerItem("Demo");
    fireEvent.click(within(item).getByRole("button", { name: "Conectar" }));

    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "https://provider.example/authorize?state=opaque"
      )
    );
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/social/demo/authorize");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      return_path: "/settings",
    });
  });

  test("shows the connect error when authorize fails", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response()))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockResolvedValueOnce(jsonResponse({}, 500));

    render(<SocialConnections locale="es" />);
    await screen.findByRole("heading", { name: "Demo" });
    const item = providerItem("Demo");
    fireEvent.click(within(item).getByRole("button", { name: "Conectar" }));

    expect(
      await screen.findByText(
        "No se pudo iniciar la conexión. Vuelve a intentarlo."
      )
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No pudimos cargar las conexiones sociales.")
    ).not.toBeInTheDocument();
  });

  test("shows the check error when checking fails", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response([connection()])))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockResolvedValueOnce(jsonResponse({}, 500));

    render(<SocialConnections locale="es" />);
    await screen.findByRole("heading", { name: "Cuenta demo" });
    fireEvent.click(screen.getByRole("button", { name: "Comprobar conexión" }));

    expect(
      await screen.findByText(
        "No se pudo comprobar la conexión. Vuelve a intentarlo."
      )
    ).toBeInTheDocument();
  });

  test("shows the disconnect error after confirming a failed disconnect", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response([connection()])))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockResolvedValueOnce(jsonResponse({}, 500));

    render(<SocialConnections locale="es" />);
    await screen.findByRole("heading", { name: "Cuenta demo" });
    fireEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Confirmar desconexión" })
    );

    expect(
      await screen.findByText(
        "No se pudo desconectar la cuenta. Vuelve a intentarlo."
      )
    ).toBeInTheDocument();
  });

  test("shows the connecting label while authorize is in flight", async () => {
    let resolveAuthorize: (value: Response) => void = () => undefined;
    const authorizePending = new Promise<Response>((resolve) => {
      resolveAuthorize = resolve;
    });
    const assign = vi.fn<[url: string | URL], void>();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response()))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockReturnValueOnce(authorizePending);

    render(
      <SocialConnections
        locale="es"
        navigateToAuthorization={(url) => assign(url)}
      />
    );
    await screen.findByRole("heading", { name: "Demo" });
    const item = providerItem("Demo");
    fireEvent.click(within(item).getByRole("button", { name: "Conectar" }));

    expect(
      await within(item).findByRole("button", { name: "Conectando…" })
    ).toBeInTheDocument();
    resolveAuthorize(
      jsonResponse({
        provider: "demo",
        authorization_url: "https://provider.example/authorize?state=opaque",
      })
    );
    await waitFor(() => expect(assign).toHaveBeenCalled());
  });

  test("check calls the endpoint and replaces the connection row", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response([connection()])))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockResolvedValueOnce(
        jsonResponse({
          connection: connection({
            status: "expired",
            last_checked_at: "2026-08-02T12:00:00Z",
          }),
        })
      );

    render(<SocialConnections locale="es" />);
    await screen.findByRole("heading", { name: "Cuenta demo" });
    fireEvent.click(screen.getByRole("button", { name: "Comprobar conexión" }));

    await waitFor(() =>
      expect(screen.getByText("Expirada")).toBeInTheDocument()
    );
    expect(fetchMock.mock.calls[2]?.[0]).toBe(
      "/api/v1/social/connections/connection-1/check"
    );
  });

  test("requires confirmation before disconnecting, then refreshes after DELETE", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response([connection()])))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockResolvedValueOnce(
        jsonResponse({ connection: connection({ status: "disconnected" }) })
      )
      .mockResolvedValueOnce(jsonResponse(response()));

    render(<SocialConnections locale="es" />);
    await screen.findByRole("heading", { name: "Cuenta demo" });
    fireEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    expect(screen.getByText("¿Desconectar esta cuenta?")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole("button", { name: "Confirmar desconexión" })
    );
    await waitFor(() =>
      expect(
        screen.getByText("Aún no hay cuentas sociales conectadas.")
      ).toBeInTheDocument()
    );
    expect(fetchMock.mock.calls[2]?.[0]).toBe(
      "/api/v1/social/connections/connection-1"
    );
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("DELETE");
  });

  test("shows the disconnecting label while DELETE is in flight", async () => {
    let resolveDisconnect: (value: Response) => void = () => undefined;
    const disconnectPending = new Promise<Response>((resolve) => {
      resolveDisconnect = resolve;
    });
    fetchMock
      .mockResolvedValueOnce(jsonResponse(response([connection()])))
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-value" }))
      .mockReturnValueOnce(disconnectPending)
      .mockResolvedValueOnce(jsonResponse(response()));

    render(<SocialConnections locale="es" />);
    await screen.findByRole("heading", { name: "Cuenta demo" });
    fireEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Confirmar desconexión" })
    );

    expect(
      await screen.findByRole("button", { name: "Desconectando…" })
    ).toBeInTheDocument();
    resolveDisconnect(
      jsonResponse({ connection: connection({ status: "disconnected" }) })
    );
    await screen.findByText("Aún no hay cuentas sociales conectadas.");
  });

  test("renders each locale with translated copy, without keys or undefined", async () => {
    const expected: Record<"es" | "en" | "pt", string> = {
      es: "Conexiones sociales",
      en: "Social connections",
      pt: "Conexões sociais",
    };

    for (const locale of ["es", "en", "pt"] as const) {
      fetchMock.mockResolvedValueOnce(jsonResponse(response()));
      const view = render(<SocialConnections locale={locale} />);
      expect(
        await screen.findByRole("heading", { name: expected[locale] })
      ).toBeInTheDocument();
      expect(document.body.textContent).not.toMatch(
        /settings\.social|undefined/i
      );
      view.unmount();
    }
  });

  test("handles a connected callback, reloads, and clears the URL before a reload can repeat it", async () => {
    configureSettingsPage();
    navigation.query = "social=connected&provider=demo";
    fetchMock.mockResolvedValueOnce(jsonResponse(response()));

    const view = render(<SettingsPage />);

    expect(
      await screen.findByText("La cuenta de Demo se conectó correctamente.")
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith("/settings")
    );
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/social/connections");

    view.unmount();
    navigation.query = "";
    navigation.replace.mockReset();
    fetchMock.mockResolvedValueOnce(jsonResponse(response()));
    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "Configuración" });
    expect(
      screen.queryByText("La cuenta de Demo se conectó correctamente.")
    ).not.toBeInTheDocument();
  });

  test("handles a denied callback without echoing an untrusted parameter", async () => {
    configureSettingsPage();
    navigation.query = "social=error&reason=denied";
    fetchMock.mockResolvedValueOnce(jsonResponse(response()));

    render(<SettingsPage />);

    expect(
      await screen.findByText("La conexión fue cancelada en el proveedor.")
    ).toBeInTheDocument();
    expect(screen.queryByText("denied")).not.toBeInTheDocument();
  });

  test("has no publish control and never stores or renders secrets", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(response([connection({ display_name: "Cuenta segura" })]))
    );

    const { container } = render(<SocialConnections locale="en" />);
    await screen.findByRole("heading", { name: "Cuenta segura" });

    expect(container.textContent).not.toMatch(
      /publish|post now|access_token|secret/i
    );
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
