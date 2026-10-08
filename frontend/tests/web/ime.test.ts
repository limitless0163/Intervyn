import { describe, expect, it } from "vitest";
import { isImeConfirm } from "../../src/utils/ime";

describe("IME form submission guard", () => {
  it("reserves Enter for candidate selection during composition", () => {
    expect(isImeConfirm({ key: "Enter", isComposing: true, keyCode: 13 })).toBe(
      true,
    );
  });

  it("handles Safari's composition-confirm Enter", () => {
    expect(
      isImeConfirm({ key: "Enter", isComposing: false, keyCode: 229 }),
    ).toBe(true);
  });

  it("allows ordinary Enter to submit and leaves other composition keys alone", () => {
    expect(
      isImeConfirm({ key: "Enter", isComposing: false, keyCode: 13 }),
    ).toBe(false);
    expect(isImeConfirm({ key: "a", isComposing: true, keyCode: 229 })).toBe(
      false,
    );
  });
});
