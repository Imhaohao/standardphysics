import { ArrowsOutCardinal, MinusCircle, PlusCircle } from "@phosphor-icons/react";
import type { ChangeType } from "@/lib/room-changes";

const ICONS = { moved: ArrowsOutCardinal, added: PlusCircle, removed: MinusCircle } as const;

/** The shape that tells moved, new and gone apart without relying on colour. */
export function ChangeTypeIcon({ type, size = 18 }: { type: ChangeType; size?: number }) {
  const Icon = ICONS[type];
  return <Icon size={size} weight="bold" aria-hidden className="change-tone shrink-0" />;
}
