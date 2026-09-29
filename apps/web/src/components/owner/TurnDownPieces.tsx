"use client";

import { Prohibit } from "@phosphor-icons/react";
import { useId, useState } from "react";
import { SavedWishes } from "@/components/proposal/ProposalReview";
import type { ProposalReviewState } from "@/components/proposal/useProposalReview";
import { Button } from "@/components/ui/Button";
import { backSentence, namedPieces, type Piece, turnDownRequest } from "@/lib/turn-down";
import type { NodeMove, SceneGraph } from "@/types/contracts";

type Props = {
  review: ProposalReviewState;
  scene: SceneGraph;
  revision: number;
  /** Every move on the plan, the owner's own and the suggestion's. */
  moves: NodeMove[];
  /** The pieces the model moved, which the owner can turn down. */
  proposed: Set<string>;
  model: string;
  /** Whether this list also shows what the owner asked to keep, when no finding's review already does. */
  showSaved: boolean;
  onTurnedDown: (nodeIds: string[]) => void;
  onPreview: (nodeId: string | null) => void;
};

function pieceKey(ids: string[]): string {
  return [...ids].sort().join("|");
}

/** On the plan a Fix room run loaded: turn down where the model put a piece, so no later suggestion puts it there. */
export function TurnDownPieces({ review, scene, revision, moves, proposed, model, showSaved, onTurnedDown, onPreview }: Props) {
  const headingId = useId();
  /** What the last turn-down put back, said only while the pieces it left outlined are still the ones shown. */
  const [done, setDone] = useState<{ sentence: string; left: string } | null>(null);
  const pieces = namedPieces(scene, moves.filter((move) => proposed.has(move.node_id)));
  const shown = pieceKey(pieces.map((piece) => piece.move.node_id));

  function turnDown(chosen: Piece[]) {
    const body = turnDownRequest(chosen.map((piece) => piece.move), pieces.map((piece) => piece.move), revision, model);
    if (!body || review.looking) return;
    review.turnDown(body, () => {
      onTurnedDown(chosen.map((piece) => piece.move.node_id));
      const gone = new Set(chosen.map((piece) => piece.move.node_id));
      const left = pieceKey(pieces.map((piece) => piece.move.node_id).filter((id) => !gone.has(id)));
      setDone({ sentence: backSentence(chosen.map((piece) => piece.name)), left });
    });
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      {pieces.length > 0 && (
        <>
          <h2 id={headingId} className="text-lg font-semibold">Moved by {model}</h2>
          <ul className="flex flex-col">
            {pieces.map((piece) => (
              <li key={piece.move.node_id} className="flex min-h-11 items-center justify-between gap-3"
                onMouseEnter={() => onPreview(piece.move.node_id)} onMouseLeave={() => onPreview(null)}>
                <span className="first-letter:uppercase">{piece.name}</span>
                <Button variant="quiet" aria-disabled={review.looking} aria-label={`Don't put the ${piece.name} here`}
                  onFocus={() => onPreview(piece.move.node_id)} onClick={() => turnDown([piece])}>
                  <Prohibit size={16} aria-hidden />
                  Don&apos;t put it here
                </Button>
              </li>
            ))}
          </ul>
          {pieces.length > 1 && (
            <Button variant="choice" className="justify-center" aria-disabled={review.looking} onClick={() => turnDown(pieces)}>
              Don&apos;t put any of them here
            </Button>
          )}
        </>
      )}
      <p role="status" className="text-pretty text-ink-muted empty:hidden">{done?.left === shown ? done.sentence : null}</p>
      {review.failed && <p role="alert" className="text-problem">Unable to save that. Check your connection and try again.</p>}
      {showSaved && <SavedWishes review={review} findingId={null} onRelook={() => undefined} />}
    </section>
  );
}
