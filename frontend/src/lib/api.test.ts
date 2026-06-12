import { describe, expect, it } from "vitest";
import { fmtNaira, fmtPct } from "./api";

describe("formatters", () => {
  it("formats naira with symbol and two decimals", () => {
    expect(fmtNaira(1480.5)).toBe("\u20a61,480.50");
  });
  it("signs percentages", () => {
    expect(fmtPct(6.525)).toBe("+6.53%");
    expect(fmtPct(-0.1)).toBe("-0.10%");
  });
});
