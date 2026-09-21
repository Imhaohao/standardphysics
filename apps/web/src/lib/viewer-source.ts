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

/** Whether the splat room is what the viewer actually puts on screen.

Asking for splats is not enough to see them: a scan that never had any falls
back to the scanned mesh, and a scan with neither falls back to the boxes. The
viewer and the chrome around it have to agree on which of the three is showing,
so both ask here rather than each working it out.
*/
export function showsSplats({
  materialMode,
  hasSplats,
  hasScanGlb,
}: {
  materialMode: ViewerMaterialMode;
  hasSplats: boolean;
  hasScanGlb: boolean;
}): boolean {
  if (materialMode === "splat") return hasSplats;
  return materialMode === "scan" && !hasScanGlb && hasSplats;
}
