import { describe, expect, it } from "vitest";
import { backSentence, namedPieces, turnDownRequest } from "./turn-down";
import { wishKey } from "./owner-wishes";
import type { NodeMove, OwnerWish, SceneGraph } from "@/types/contracts";

const scene = { nodes: [{ id: "a", label: "Chair" }, { id: "b", label: "Chair" }, { id: "c", label: "Trash can" }] } as unknown as SceneGraph;
const move = (id: string): NodeMove => ({ node_id: id, delta_translation: { x: 0.5, y: 0, z: 0 }, delta_rotation_z_degrees: 0 });

describe("turning down pieces", () => {
  it("names twins apart so two chairs never read the same", () => {
    expect(namedPieces(scene, [move("a"), move("b"), move("c")]).map((piece) => piece.name))
      .toEqual(["chair (1 of 2)", "chair (2 of 2)", "trash can"]);
  });

  it("says what went back and that it will not come back there", () => {
    expect(backSentence(["chair"])).toBe("The chair is back where it was. No suggestion will put it there again.");
    expect(backSentence(["chair", "trash can"])).toBe("Those 2 pieces are back where they were. No suggestion will put them there again.");
  });

  it("sends nothing when no piece was chosen, and the whole suggestion with any that were", () => {
    expect(turnDownRequest([], [move("a")], 0, "Kimi K3")).toBeNull();
    expect(turnDownRequest([move("a")], [move("a"), move("c")], 3, "Kimi K3"))
      .toEqual({ base_revision: 3, turned_down: [move("a")], suggestion: [move("a"), move("c")], source: "fix_room", model: "Kimi K3" });
  });

  it("keeps two turned-down spots for one piece as two wishes", () => {
    const spot = (x: number): OwnerWish => ({ kind: "not_there", node_id: "a", anchor_id: null, at: { x, y: 0, z: 0 }, inches: 18, text: "" });
    expect(wishKey(spot(1))).not.toBe(wishKey(spot(2)));
  });
});
