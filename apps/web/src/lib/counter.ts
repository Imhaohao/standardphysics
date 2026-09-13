import type { SceneNode } from "@/types/contracts";

/** The label the API gives an object the owner marks, matching `labels.SERVICE_COUNTER_LABEL`. */
export const SERVICE_COUNTER_LABEL = "service counter";

export const canBeCounter = (node: SceneNode) => node.kind === "object";

export const isMarkedCounter = (node: SceneNode) => node.labeled_by === "owner" && node.label === SERVICE_COUNTER_LABEL;

/** Scanned categories arrive capitalised and owner labels arrive lower case, so the chip shows both the same way. */
export const pieceName = (label: string) => label.charAt(0).toUpperCase() + label.slice(1);
