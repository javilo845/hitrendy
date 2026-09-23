import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { GoogleSignInButton } from "@/components/auth/google-sign-in-button";
import { api } from "@/lib/api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GoogleSignInButton", () => {
  test("muestra el botón deshabilitado cuando Google no está configurado", async () => {
    vi.spyOn(api.auth.google, "status").mockResolvedValue({ configured: false });

    render(<GoogleSignInButton />);

    const button = await screen.findByRole("button", { name: "Continuar con Google" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Google no está disponible en este momento.")).toBeInTheDocument();
  });

  test("muestra un error comprensible si no puede iniciar el redirect", async () => {
    vi.spyOn(api.auth.google, "status").mockResolvedValue({ configured: true });
    vi.spyOn(api.auth.google, "start").mockRejectedValue(new Error("network"));

    render(<GoogleSignInButton />);

    const button = await screen.findByRole("button", { name: "Continuar con Google" });
    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "No pudimos iniciar el acceso con Google."
      );
    });
    expect(button).not.toBeDisabled();
  });
});
