import type { NodeMove, SceneGraph, TurnDownRequest } from "@/types/contracts";

export type Piece = { move: NodeMove; name: string };

/** Each moved piece by its label, numbered "(1 of 2)" when two share one. */
export function namedPieces(scene: SceneGraph, moves: NodeMove[]): Piece[] {
  const labels = moves.map((move) => (scene.nodes.find((node) => node.id === move.node_id)?.label ?? "Piece").toLowerCase());
  return moves.map((move, index) => {
    const total = labels.filter((label) => label === labels[index]).length;
    const nth = labels.slice(0, index + 1).filter((label) => label === labels[index]).length;
    return { move, name: total > 1 ? `${labels[index]} (${nth} of ${total})` : labels[index] };
  });
}

export function backSentence(names: string[]): string {
  if (names.length === 1) return `The ${names[0]} is back where it was. No suggestion will put it there again.`;
  return `Those ${names.length} pieces are back where they were. No suggestion will put them there again.`;
}

export function turnDownRequest(chosen: NodeMove[], suggestion: NodeMove[], revision: number, model: string): TurnDownRequest | null {
  const [first, ...rest] = chosen;
  if (!first) return null;
  return { base_revision: revision, turned_down: [first, ...rest], suggestion, source: "fix_room", model };
}
