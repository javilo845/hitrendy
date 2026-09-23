import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Composer } from "@/components/assistant/composer";

const draftStorageKey = (conversationId: string) =>
  `hitrendy:composer-draft:${conversationId}`;

describe("Composer", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  test("preserves an isolated draft for each conversation", async () => {
    const { rerender } = render(
      <Composer onSend={vi.fn()} disabled={false} draftKey="conversation-a" />
    );
    const input = screen.getByRole("textbox", { name: "Mensaje" });

    fireEvent.change(input, { target: { value: "Borrador de A" } });
    expect(window.localStorage.getItem(draftStorageKey("conversation-a"))).toBe(
      "Borrador de A"
    );

    rerender(
      <Composer onSend={vi.fn()} disabled={false} draftKey="conversation-b" />
    );
    await waitFor(() => expect(input).toHaveValue(""));

    fireEvent.change(input, { target: { value: "Borrador de B" } });
    rerender(
      <Composer onSend={vi.fn()} disabled={false} draftKey="conversation-a" />
    );

    await waitFor(() => expect(input).toHaveValue("Borrador de A"));
  });

  test("clears the current conversation draft after sending", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} disabled={false} draftKey="conversation-a" />);

    fireEvent.change(screen.getByRole("textbox", { name: "Mensaje" }), {
      target: { value: "Mensaje pendiente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    expect(onSend).toHaveBeenCalledWith("Mensaje pendiente", []);
    expect(window.localStorage.getItem(draftStorageKey("conversation-a"))).toBeNull();
  });

  test("attaches a pasted image and sends it as an asset", async () => {
    const onSend = vi.fn();
    const onUploadImage = vi.fn().mockResolvedValue("asset_123");
    render(
      <Composer
        onSend={onSend}
        disabled={false}
        draftKey="conversation-a"
        onUploadImage={onUploadImage}
      />
    );

    const file = new File(["binario"], "captura.png", { type: "image/png" });
    fireEvent.paste(screen.getByRole("textbox", { name: "Mensaje" }), {
      clipboardData: { files: [file], getData: () => "" },
    });

    await waitFor(() => expect(onUploadImage).toHaveBeenCalledWith(file));
    await screen.findByText("captura.png");

    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    // No text was typed, so the composer supplies the analysis request itself.
    expect(onSend).toHaveBeenCalledWith("Analiza esta imagen para mi negocio.", [
      "asset_123",
    ]);
  });
});
