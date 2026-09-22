export type ViewerMaterialMode = "reconstructed" | "captured" | "plain" | "coverage" | "scan" | "splat";

type ViewerSourceInput = {
  materialMode: ViewerMaterialMode;
  hasCleanGlb: boolean;
  hasPhotoBuild: boolean;
  staleNodeIds: string[];
};

/** Selects the source-specific rules that keep a current clean GLB independent of an older photo build. */
export function viewerSourcePlan({ materialMode, hasCleanGlb, hasPhotoBuild, staleNodeIds }: ViewerSourceInput) {
  const usePhotoBuild = hasPhotoBuild && (materialMode === "captured" || materialMode === "coverage");
  return {
    usePhotoBuild,
    staleNodeIds: usePhotoBuild ? staleNodeIds : [],
    materialMode: materialMode === "scan" || usePhotoBuild || hasCleanGlb ? materialMode : "plain" as const,
  };
}

type ShowsSplatsInput = {
  materialMode: ViewerMaterialMode;
  hasSplats: boolean;
  hasScanGlb: boolean;
};

/** Splats are a preview source only: on, only in splat mode, and never over a measured scan's own GLB. */
export function showsSplats({ materialMode, hasSplats, hasScanGlb }: ShowsSplatsInput): boolean {
  return materialMode === "splat" && hasSplats && !hasScanGlb;
}
