import { describe, expect, it } from "vitest";

import { wrapRailOffset } from "@/components/landing/poster-rail";

describe("wrapRailOffset", () => {
  it("keeps the animation clock inside one centered cycle", () => {
    expect(wrapRailOffset(0, 100)).toBe(0);
    expect(wrapRailOffset(260, 100)).toBe(-40);
    expect(wrapRailOffset(-260, 100)).toBe(40);
  });

  it("does not accumulate an unbounded animation value", () => {
    const wrapped = wrapRailOffset(Number.MAX_SAFE_INTEGER, 640);

    expect(wrapped).toBeGreaterThanOrEqual(-320);
    expect(wrapped).toBeLessThan(320);
  });

  it("returns zero while the layout has no measurable width", () => {
    expect(wrapRailOffset(120, 0)).toBe(0);
  });
});
