import { describe, test, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { GeneratedArtifactCard } from "@/components/generated-artifact-card";
import type { GeneratedSocialPost } from "@/types/artifact";

const mockArtifact: GeneratedSocialPost = {
  artifact_type: "social_post",
  platform: "instagram",
  hook: "Tu próximo antojo ya tiene nombre ✨",
  caption: "Presenta aquí una propuesta personalizada por HiTrendy.",
  call_to_action: "Visítanos y conócela.",
  hashtags: ["#HiTrendy", "#ContenidoParaNegocios"],
  visual_direction:
    "Producto en primer plano, preparación y ambiente del negocio.",
  format_recommendation: "reel",
  assumptions: [],
};

describe("GeneratedArtifactCard", () => {
  test("renders artifact content correctly", () => {
    render(<GeneratedArtifactCard artifact={mockArtifact} />);

    expect(
      screen.getByText("Tu próximo antojo ya tiene nombre ✨")
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Presenta aquí una propuesta personalizada por HiTrendy."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("Visítanos y conócela.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Producto en primer plano, preparación y ambiente del negocio."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText("#HiTrendy #ContenidoParaNegocios")
    ).toBeInTheDocument();
  });

  test("triggers callback on save project button click", () => {
    const onSaveMock = vi.fn();
    render(
      <GeneratedArtifactCard artifact={mockArtifact} onSave={onSaveMock} />
    );

    const saveButton = screen.getByRole("button", { name: "Guardar proyecto" });
    fireEvent.click(saveButton);

    expect(onSaveMock).toHaveBeenCalledOnce();
  });

  test("triggers callback with correct args on variation button clicks", () => {
    const onVariationMock = vi.fn();
    render(
      <GeneratedArtifactCard
        artifact={mockArtifact}
        onVariation={onVariationMock}
      />
    );

    const shorterButton = screen.getByRole("button", { name: "Más corto" });
    fireEvent.click(shorterButton);
    expect(onVariationMock).toHaveBeenCalledWith("shorter");

    const moreYouthfulButton = screen.getByRole("button", {
      name: "Más juvenil",
    });
    fireEvent.click(moreYouthfulButton);
    expect(onVariationMock).toHaveBeenCalledWith("more_youthful");

    fireEvent.click(screen.getByRole("button", { name: "Más profesional" }));
    expect(onVariationMock).toHaveBeenCalledWith("more_professional");

    fireEvent.click(screen.getByRole("button", { name: "Más amigable" }));
    expect(onVariationMock).toHaveBeenCalledWith("more_friendly");
  });

  test("copies the structured post and reports success", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<GeneratedArtifactCard artifact={mockArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "Copiar contenido" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining(mockArtifact.caption));
    expect(screen.getByRole("status")).toHaveTextContent("Contenido copiado.");
  });
});
