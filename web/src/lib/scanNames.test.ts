import { describe, expect, it } from "vitest";
import { scanChangesFrom } from "./scanNames";

describe("renaming a scan", () => {
  it("trims both names and clears an empty shop name", () => {
    expect(scanChangesFrom("  Front of house ", " Corner shop ")).toEqual({ changes: { name: "Front of house", site_name: "Corner shop" }, error: null });
    expect(scanChangesFrom("Front of house", "   ").changes).toEqual({ name: "Front of house", site_name: null });
  });

  it("needs a scan name and keeps both names short", () => {
    expect(scanChangesFrom(" ", "Corner shop").error).toMatch(/Give the scan a name/);
    expect(scanChangesFrom("x".repeat(201), "").error).toMatch(/under 200/);
  });
});
