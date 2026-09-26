import { describe, expect, it } from "vitest";
import type { Finding } from "@/types/contracts";
import { isBeingChecked, PHOTO_BEING_CHECKED_TITLE, splitQuestions } from "./reportCounts";

const citation = { authority: "ADA_2010", edition: "2010 ADA Standards", section: "404.2.7", url: null } as const;

function question(id: string, title: string, asks: Finding["asks"] = "photo"): Finding {
  return {
    id, check_id: id, outcome: "question", title, detail: "", fix: null, asks,
    measured_inches: null, required_inches: null, citation, locus: null,
  };
}

describe("splitQuestions", () => {
  it("leaves a photo the owner already sent out of what is still to send", () => {
    const handle = question("door_hardware", PHOTO_BEING_CHECKED_TITLE);
    const doorway = question("door_clear_width", "Measure the front doorway and send us the number", "measurement");
    const floor = question("floor_surface", "Send a photo of the floor just inside the front door");

    const { toSend, beingChecked } = splitQuestions([handle, doorway, floor]);

    expect(toSend.map((finding) => finding.id)).toEqual(["door_clear_width", "floor_surface"]);
    expect(beingChecked.map((finding) => finding.id)).toEqual(["door_hardware"]);
  });

  it("counts every question as still to send before any photo arrives", () => {
    const questions = [question("a", "Send a photo of the front door handle"), question("b", "Send a photo of the front doorway from the side")];
    expect(splitQuestions(questions)).toEqual({ toSend: questions, beingChecked: [] });
  });
});

describe("isBeingChecked", () => {
  it("only marks a question, never a result that happens to share the title", () => {
    const result = { ...question("a", PHOTO_BEING_CHECKED_TITLE), outcome: "passes" as const };
    expect(isBeingChecked(result)).toBe(false);
  });
});
