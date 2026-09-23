import { describe, expect, test } from "vitest";

import { isApprovedCanvaUrl } from "@/components/studio/instagram-post-flow";
import { instagramFlowCopy } from "@/lib/instagram-flow-copy";

describe("flujo de post Instagram", () => {
  test("incluye todas las claves de interfaz para es, en y pt", () => {
    const keys = Object.keys(instagramFlowCopy.es);
    for (const locale of [instagramFlowCopy.en, instagramFlowCopy.pt]) {
      expect(Object.keys(locale)).toEqual(keys);
      expect(Object.values(locale).every(Boolean)).toBe(true);
    }
  });

  test("allowlistea exclusivamente las URLs aprobadas de Canva", () => {
    expect(isApprovedCanvaUrl("https://canva.link/jxr6r3xdtdx3p18")).toBe(true);
    expect(isApprovedCanvaUrl("https://canva.com/unsafe")).toBe(false);
    expect(isApprovedCanvaUrl("https://evil.example/canva")).toBe(false);
    expect(isApprovedCanvaUrl(undefined)).toBe(false);
  });
});
