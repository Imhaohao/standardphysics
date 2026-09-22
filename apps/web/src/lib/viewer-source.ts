export type ViewerMaterialMode = "reconstructed" | "captured" | "plain" | "coverage" | "scan" | "splat";

type ViewerSourceInput = {
  materialMode: ViewerMaterialMode;
  hasCleanGlb: boolean;
  hasPhotoBuild: boolean;
  staleNodeIds: string[];
};

/**
 * Whether the splats are the surface on screen, rather than the painted mesh or the boxes.
 *
 * Splat mode is the splats. Scan mode prefers the painted mesh and only falls back to the
 * splats when no mesh has been baked, so the caveats and the load error that belong to the
 * splats follow this rather than following the mode name.
 */
export function showsSplats({ materialMode, hasSplats, hasScanGlb }: { materialMode: ViewerMaterialMode; hasSplats: boolean; hasScanGlb: boolean }) {
  if (!hasSplats) return false;
  if (materialMode === "splat") return true;
  return materialMode === "scan" && !hasScanGlb;
}

/** Selects the source-specific rules that keep a current clean GLB independent of an older photo build. */
export function viewerSourcePlan({ materialMode, hasCleanGlb, hasPhotoBuild, staleNodeIds }: ViewerSourceInput) {
  const usePhotoBuild = hasPhotoBuild && (materialMode === "captured" || materialMode === "coverage");
  return {
    usePhotoBuild,
    staleNodeIds: usePhotoBuild ? staleNodeIds : [],
    materialMode: materialMode === "scan" || materialMode === "splat" || usePhotoBuild || hasCleanGlb ? materialMode : "plain" as const,
  };
}
