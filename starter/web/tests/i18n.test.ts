import { describe, expect, test } from "vitest";
import { appCopy, supportedLocales } from "@/lib/i18n";

describe("global translations", () => {
  test("keeps the same visible key shape for Spanish, English, and Portuguese", () => {
    const shape = (value: unknown): unknown => {
      if (Array.isArray(value)) return value.map(shape);
      if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, shape(item)]));
      return true;
    };
    const expected = JSON.stringify(shape(appCopy.es));
    for (const locale of supportedLocales) {
      expect(JSON.stringify(shape(appCopy[locale]))).toBe(expected);
      expect(JSON.stringify(appCopy[locale])).not.toContain("undefined");
    }
  });
});
