import { describe, expect, it } from "vitest";
import { showsSplats, viewerSourcePlan } from "./viewer-source";

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
});
