import { describe, test, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProgressBar } from "@/components/onboarding/progress-bar";

describe("ProgressBar", () => {
  const steps = ["Paso 1", "Paso 2", "Paso 3"];

  test("renders correct step label", () => {
    render(<ProgressBar steps={steps} current={0} />);
    expect(screen.getByText("Paso 1 de 3: Paso 1")).toBeInTheDocument();
  });

  test("renders progress indicators", () => {
    const { container } = render(<ProgressBar steps={steps} current={1} />);
    const indicators = container.querySelectorAll("li");
    expect(indicators).toHaveLength(3);
  });
});

describe("StepBusiness", () => {
  test("renders form fields", async () => {
    const { StepBusiness } =
      await import("@/components/onboarding/step-business");
    const data = {
      name: "",
      category: "" as const,
      country: "",
      city: "",
      description: "",
      primary_product: "",
      target_audience: "",
      website_url: "",
    };
    const onChange = () => {};

    render(<StepBusiness data={data} onChange={onChange} />);
    expect(screen.getByLabelText(/Nombre comercial/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Categoría/)).toBeInTheDocument();
  });
});

describe("StepChannels", () => {
  test("renders platform checkboxes", async () => {
    const { StepChannels } =
      await import("@/components/onboarding/step-channels");
    const data = { preferred_platforms: [], primary_objective: "" as const };
    const onChange = () => {};

    render(<StepChannels data={data} onChange={onChange} />);
    expect(screen.getByLabelText("Instagram")).toBeInTheDocument();
    expect(screen.getByLabelText("TikTok")).toBeInTheDocument();
  });
});
