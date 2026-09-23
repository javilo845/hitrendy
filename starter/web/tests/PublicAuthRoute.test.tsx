import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { PublicAuthRoute } from "@/components/auth/public-auth-route";
import { ApiError } from "@/lib/api";

const replace = vi.fn();
// Stable across renders, like the real App Router hook: a fresh object each
// render would re-fire every effect that depends on it.
const router = { replace, refresh: vi.fn() };

vi.mock("next/navigation", () => ({
  usePathname: () => "/login",
  useRouter: () => router,
}));

const me = vi.fn();
const getSignup = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      auth: {
        me: () => me(),
        signup: { get: () => getSignup() },
      },
    },
  };
});

function unauthenticated() {
  return new ApiError(401, "UNAUTHORIZED", "Sesión requerida.", false);
}

describe("PublicAuthRoute", () => {
  beforeEach(() => {
    replace.mockClear();
    me.mockReset();
    getSignup.mockReset();
    window.history.replaceState({}, "", "/login");
  });

  test("returns an authenticated visitor to the page they were sent from", async () => {
    // ProtectedRoute bounces here as /login?next=<page> whenever it cannot
    // verify a session. When the session turns out to be fine, dropping `next`
    // is what made every such bounce end on the dashboard.
    window.history.replaceState({}, "", "/login?next=%2Fstudio%2Fnew");
    me.mockResolvedValue({ id: "user_1" });

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/studio/new"));
  });

  test("falls back to the dashboard when no destination was requested", async () => {
    me.mockResolvedValue({ id: "user_1" });

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  test("refuses to forward an off-site destination", async () => {
    window.history.replaceState({}, "", "/login?next=https%3A%2F%2Fevil.example");
    me.mockResolvedValue({ id: "user_1" });

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  test("shows the form when the session check itself fails", async () => {
    me.mockRejectedValue(
      new ApiError(500, "INTERNAL", "Error del servidor.", true)
    );

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    expect(await screen.findByText("Formulario")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  test("reports an unreachable API instead of failing open in silence", async () => {
    me.mockRejectedValue(
      new ApiError(500, "INTERNAL", "Error del servidor.", true)
    );

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    // The form stays usable on purpose; the warning sits alongside it.
    expect(await screen.findByText("Formulario")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No pudimos contactar con el servidor."
    );
  });

  test("clears the warning when a retry reaches the API", async () => {
    me.mockRejectedValueOnce(
      new ApiError(500, "INTERNAL", "Error del servidor.", true)
    ).mockRejectedValue(unauthenticated());
    getSignup.mockRejectedValue(
      new ApiError(404, "SIGNUP_NOT_FOUND", "No hay registro.", false)
    );

    render(
      <PublicAuthRoute onPendingSignup="notice">
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    );
    expect(screen.getByText("Formulario")).toBeInTheDocument();
  });

  test("does not warn when the API answers with a clean 401", async () => {
    me.mockRejectedValue(unauthenticated());
    getSignup.mockRejectedValue(
      new ApiError(404, "SIGNUP_NOT_FOUND", "No hay registro.", false)
    );

    render(
      <PublicAuthRoute onPendingSignup="notice">
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    expect(await screen.findByText("Formulario")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("offers an unfinished registration without taking over the page", async () => {
    me.mockRejectedValue(unauthenticated());
    getSignup.mockResolvedValue({ current_step: "business" });

    render(
      <PublicAuthRoute onPendingSignup="notice">
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    expect(await screen.findByText("Formulario")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Continuar registro" })
    ).toHaveAttribute("href", "/onboarding");
    expect(replace).not.toHaveBeenCalled();
  });

  test("resumes the wizard where starting over is not possible", async () => {
    me.mockRejectedValue(unauthenticated());
    getSignup.mockResolvedValue({ current_step: "business" });

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding"));
  });

  test("renders the form when there is no registration to resume", async () => {
    me.mockRejectedValue(unauthenticated());
    getSignup.mockRejectedValue(
      new ApiError(404, "SIGNUP_NOT_FOUND", "No hay registro.", false)
    );

    render(
      <PublicAuthRoute onPendingSignup="notice">
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    expect(await screen.findByText("Formulario")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  test("sends an authenticated visitor to the dashboard", async () => {
    me.mockResolvedValue({ user: { id: "u1" } });

    render(
      <PublicAuthRoute>
        <p>Formulario</p>
      </PublicAuthRoute>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Formulario")).not.toBeInTheDocument();
  });
});
