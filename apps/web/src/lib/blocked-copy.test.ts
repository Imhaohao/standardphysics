import { describe, expect, it } from "vitest";
import { blockedSentence } from "./blocked-copy";

describe("blockedSentence", () => {
  it("names both things in a collision", () => {
    expect(blockedSentence({ node_id: "a", reason: "collided", detail: "Display case into Wall" })).toBe(
      "The display case overlaps the wall.",
    );
  });

  it("says a fixed piece stays put", () => {
    expect(blockedSentence({ node_id: "a", reason: "moved_something_fixed", detail: "Ordering counter" })).toBe(
      "The ordering counter stays where it is.",
    );
  });
});
