import { describe, expect, it } from "vitest";
import type { Proposal } from "@/types/contracts";
import { inventoryLines } from "./inventory";

const proposal = {
  id: "p", base_graph_hash: "h", moves: [], targets: [], rationale: "",
  inventory_before: { Chair: 6, Table: 4, "Display case": 2 },
  inventory_after: { Chair: 6, Table: 4, "Display case": 2 },
} as Proposal;

describe("inventoryLines", () => {
  it("shows every kind of furniture before and after", () => {
    expect(inventoryLines(proposal)).toEqual([
      "6 chairs -> 6 chairs",
      "2 display cases -> 2 display cases",
      "4 tables -> 4 tables",
    ]);
  });
});
