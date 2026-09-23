import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { axe } from "vitest-axe";

import { MessageList } from "@/components/assistant/message-list";

test("announces completed assistant messages in an accessible conversation log", async () => {
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  window.matchMedia = vi.fn().mockReturnValue({ matches: true });

  const { container } = render(
    <MessageList
      loading={false}
      messages={[
        { id: "user-1", role: "user", content: "Crea una publicación" },
        { id: "assistant-1", role: "assistant", content: "Aquí tienes tu propuesta." },
      ]}
    />
  );

  const log = screen.getByRole("log", { name: "Conversación" });
  expect(log).toHaveAttribute("aria-live", "polite");
  expect(log).toHaveAttribute("aria-busy", "false");
  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "auto" });
  const results = await axe(container, {
    rules: { "color-contrast": { enabled: false } },
  });
  expect(results.violations).toHaveLength(0);
});
