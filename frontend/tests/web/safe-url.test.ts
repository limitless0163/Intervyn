import { expect, it } from "vitest";
import { safeExternalUrl } from "../../src/utils/safe-url";

it.each([
  "javascript:alert(1)",
  "data:text/html,hello",
  "file:///private/cv",
  "kb://document/1",
  "/relative",
  "not a URL",
])("keeps %s as plain citation text", (value) => {
  expect(safeExternalUrl(value)).toBeNull();
});
it("preserves useful web citation URLs", () => {
  expect(safeExternalUrl("https://example.com/guide?q=STAR#answers")).toBe(
    "https://example.com/guide?q=STAR#answers",
  );
});
