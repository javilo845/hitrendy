import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { StudioWorkspace } from "@/components/studio/studio-workspace";
import { api } from "@/lib/api";

const router = {
  push: vi.fn(),
  replace: vi.fn(),
};

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
      public retryable = false
    ) {
      super(message);
    }
  },
  createIdempotencyKey: () => "studio-test-key",
  api: {
    conversations: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      sendMessage: vi.fn(),
    },
    businesses: { list: vi.fn() },
    // The header reads the real capability snapshot instead of claiming the
    // assistant is up, so every render of the workspace calls this.
    capabilities: {
      get: vi.fn().mockResolvedValue({
        advisor: { status: "available", tier: "free", quality_levels: ["fast"] },
        vision_review: {
          status: "available",
          tier: "free",
          quality_levels: ["fast"],
        },
      }),
    },
    assets: { upload: vi.fn() },
    projects: { create: vi.fn() },
    artifacts: {
      event: vi.fn(),
      createVariation: vi.fn(),
      feedback: vi.fn(),
    },
  },
}));

describe("StudioWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.conversations.list).mockResolvedValue([
      {
        id: "conversation-1",
        title: "Promoción de agosto",
        status: "active",
        last_message: "Preparemos el anuncio.",
      },
    ]);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
  });

  test("abre el historial como menú, busca y devuelve el foco al cerrar", async () => {
    render(<StudioWorkspace />);

    const workspace = screen.getByRole("region", {
      name: "Studio de contenido",
    });
    const toggle = screen.getByRole("button", {
      name: "Ver el historial",
    });
    const panel = screen.getByRole("complementary", {
      name: "Conversaciones",
    });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(panel).not.toHaveAttribute("data-open");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(panel).toHaveAttribute("data-open");
    await screen.findByText("Promoción de agosto");

    fireEvent.click(
      screen.getByRole("button", { name: "Buscar en el historial" })
    );
    const search = screen.getByRole("searchbox", {
      name: "Buscar conversaciones",
    });
    expect(search).toHaveFocus();
    fireEvent.change(search, { target: { value: "promo" } });

    await waitFor(() =>
      expect(api.conversations.list).toHaveBeenLastCalledWith({
        status: "active",
        search: "promo",
      })
    );

    fireEvent.keyDown(workspace, { key: "Escape" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(panel).not.toHaveAttribute("data-open");
    expect(toggle).toHaveFocus();
  });
});
