import { describe, expect, test } from "vitest";

import { isSafeNextPath, loginPath, resolveNextPath } from "@/lib/routes";

describe("rutas protegidas", () => {
  test("acepta únicamente destinos internos permitidos", () => {
    expect(isSafeNextPath("/dashboard")).toBe(true);
    expect(isSafeNextPath("/trends")).toBe(true);
    expect(isSafeNextPath("/templates")).toBe(true);
    expect(isSafeNextPath("/studio/conversation_42")).toBe(true);
    expect(isSafeNextPath("//example.com")).toBe(false);
    expect(isSafeNextPath("https://example.com")).toBe(false);
    expect(isSafeNextPath("/projects")).toBe(false);
  });

  test("usa dashboard como destino seguro por defecto", () => {
    expect(resolveNextPath("https://example.com")).toBe("/dashboard");
    expect(resolveNextPath("/settings")).toBe("/settings");
    expect(loginPath("/templates")).toBe("/login?next=%2Ftemplates");
  });
});
