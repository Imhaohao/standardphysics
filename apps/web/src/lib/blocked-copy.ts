import type { Blocked } from "@/types/contracts";
import { MAX_TRAVEL_METERS, METERS_PER_INCH } from "@/types/geometry-rules";

const INCHES_PER_FOOT = 12;

/** The travel limit as the owner reads it: 60 inches is "5 feet". */
const TRAVEL_FEET = Math.round((MAX_TRAVEL_METERS / METERS_PER_INCH / INCHES_PER_FOOT) * 10) / 10;

function lower(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

function pair(detail: string): [string, string] {
  const [moved, other = "something"] = detail.split(" into ");
  return [moved, lower(other.replace(/^the /i, ""))];
}

const SENTENCE: Record<string, (detail: string) => string> = {
  collided: (detail) => {
    const [moved, other] = pair(detail);
    return `The ${lower(moved)} overlaps the ${other}.`;
  },
  blocked_a_door: (detail) => {
    const [moved, door] = pair(detail);
    return `The ${lower(moved)} is in the way of the ${door}.`;
  },
  moved_something_fixed: (detail) => `The ${lower(detail)} stays where it is.`,
  left_the_floor: (detail) => `The ${lower(detail)} would go past the edge of the room.`,
  moved_too_far: (detail) => `The ${lower(detail)} can move up to ${TRAVEL_FEET} feet from where it was scanned.`,
  no_room_to_use: (detail) => `The ${lower(detail)} needs open floor on one side so someone can pull up to it.`,
  onto_unseen_floor: (detail) => `The ${lower(detail)} can only go on floor the scan covered.`,
};

export function blockedSentence(blocked: Blocked): string {
  const write = SENTENCE[blocked.reason];
  return write ? write(blocked.detail) : "That spot doesn't work for this piece.";
}
