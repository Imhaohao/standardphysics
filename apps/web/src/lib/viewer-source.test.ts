import { describe, expect, it } from "vitest";
import { showsSplats, viewerSourcePlan } from "./viewer-source";

describe("viewerSourcePlan", () => {
  it("does not apply an older photo build's stale shapes to a current reconstructed GLB", () => {
    expect(viewerSourcePlan({
      materialMode: "reconstructed",
      hasCleanGlb: true,
      hasPhotoBuild: true,
      staleNodeIds: ["reconstructed-node"],
    })).toEqual({ usePhotoBuild: false, staleNodeIds: [], materialMode: "reconstructed" });
  });

  it("uses stale-node fallback only while displaying the photo bake", () => {
    expect(viewerSourcePlan({
      materialMode: "captured",
      hasCleanGlb: true,
      hasPhotoBuild: true,
      staleNodeIds: ["changed-node"],
    })).toEqual({ usePhotoBuild: true, staleNodeIds: ["changed-node"], materialMode: "captured" });
  });

  it("keeps the scanned-room mode separate from the box texture build", () => {
    expect(viewerSourcePlan({
      materialMode: "scan",
      hasCleanGlb: true,
      hasPhotoBuild: true,
      staleNodeIds: ["changed-node"],
    })).toEqual({ usePhotoBuild: false, staleNodeIds: [], materialMode: "scan" });
  });

  it("does not treat the splat preview as a photo build", () => {
    expect(viewerSourcePlan({
      materialMode: "splat",
      hasCleanGlb: false,
      hasPhotoBuild: true,
      staleNodeIds: ["changed-node"],
    })).toEqual({ usePhotoBuild: false, staleNodeIds: [], materialMode: "plain" });
  });

  it("keeps the splat mode when a clean GLB stands behind it", () => {
    expect(viewerSourcePlan({
      materialMode: "splat",
      hasCleanGlb: true,
      hasPhotoBuild: true,
      staleNodeIds: ["changed-node"],
    })).toEqual({ usePhotoBuild: false, staleNodeIds: [], materialMode: "splat" });
  });
});

describe("showsSplats", () => {
  it("is only true in splat mode with assets and without a measured scan GLB", () => {
    expect(showsSplats({ materialMode: "splat", hasSplats: true, hasScanGlb: false })).toBe(true);
    expect(showsSplats({ materialMode: "splat", hasSplats: true, hasScanGlb: true })).toBe(false);
    expect(showsSplats({ materialMode: "captured", hasSplats: true, hasScanGlb: false })).toBe(false);
    expect(showsSplats({ materialMode: "splat", hasSplats: false, hasScanGlb: false })).toBe(false);
  });
});
