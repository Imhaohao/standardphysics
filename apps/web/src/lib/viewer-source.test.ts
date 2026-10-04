import { describe, expect, it } from "vitest";
import { showsSplats, shownSurface, viewerSourcePlan } from "./viewer-source";

describe("shownSurface", () => {
  const nothingCaptured = { hasSplats: false, hasScanGlb: false, combined: false };

  it("draws the painted scan in scan mode once one has been baked", () => {
    expect(shownSurface({ ...nothingCaptured, materialMode: "scan", hasScanGlb: true })).toBe("scan");
  });

  it("draws the boxes in scan mode while no scan has been baked and no splats stand in", () => {
    expect(shownSurface({ ...nothingCaptured, materialMode: "scan" })).toBe("boxes");
  });

  it("draws the splats when they are what the mode shows", () => {
    expect(shownSurface({ ...nothingCaptured, materialMode: "splat", hasSplats: true, hasScanGlb: true })).toBe("splats");
  });

  it("draws the boxes for every box mode, whatever else the scan has", () => {
    expect(shownSurface({ materialMode: "plain", hasSplats: true, hasScanGlb: true, combined: false })).toBe("boxes");
  });

  it("draws the combined walks over anything else", () => {
    expect(shownSurface({ materialMode: "scan", hasSplats: true, hasScanGlb: true, combined: true })).toBe("combined");
  });
});

describe("showsSplats", () => {
  it("shows the painted mesh rather than the splats when a scan has both", () => {
    expect(showsSplats({ materialMode: "scan", hasSplats: true, hasScanGlb: true })).toBe(false);
  });

  it("falls back to the splats in scan mode when no mesh has been baked", () => {
    expect(showsSplats({ materialMode: "scan", hasSplats: true, hasScanGlb: false })).toBe(true);
  });

  it("shows the splats in splat mode even when a painted mesh exists", () => {
    expect(showsSplats({ materialMode: "splat", hasSplats: true, hasScanGlb: true })).toBe(true);
  });

  it("shows nothing captured when the scan has no splats to show", () => {
    expect(showsSplats({ materialMode: "splat", hasSplats: false, hasScanGlb: false })).toBe(false);
  });

  it("leaves the box modes alone", () => {
    expect(showsSplats({ materialMode: "reconstructed", hasSplats: true, hasScanGlb: false })).toBe(false);
  });
});

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
    })).toEqual({ usePhotoBuild: false, staleNodeIds: [], materialMode: "splat" });
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
