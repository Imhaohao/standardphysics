import type { Api } from "@/lib/api/client";
import type { Report, Scan } from "@/lib/api/types";
import { indexSubjects } from "@/lib/scene/describe";
import type { Scene } from "@/lib/scene/types";
import { groupByElement, type ElementGroup } from "@/lib/findings/group";

/** A scan of a shop with everything a page needs to draw it. */
export interface ShopSheet {
  scan: Scan;
  scene: Scene | null;
  report: Report | null;
  groups: ElementGroup[];
  href: string;
}

export async function loadShopSheet(api: Api, scan: Scan): Promise<ShopSheet> {
  const [scene, report] = await Promise.all([api.getScene(scan.id), api.getReport(scan.id)]);
  const groups = scene && report ? groupByElement(report.findings, indexSubjects(scene)) : [];
  return { scan, scene, report, groups, href: `/shops/${encodeURIComponent(scan.id)}` };
}

export function sheetNumber(index: number) {
  return `A-${101 + index}`;
}

export function shopName(scan: Scan) {
  return scan.site_name ?? scan.name;
}

/** Things to fix: elements whose stricter result fails or still needs an answer. */
export function toFixCount(sheet: ShopSheet) {
  if (!sheet.report) return null;
  return sheet.groups.filter((group) => group.status === "fail" || group.status === "needs_info").length;
}

const STATUS_COPY: Record<string, string> = {
  capturing: "Scan in progress",
  finishing: "Checking the scan against the rules",
  complete: "Nothing to fix under ADA or California rules",
  failed: "The scan didn't finish. Try scanning again.",
};

export function scanStatusCopy(sheet: ShopSheet) {
  const toFix = toFixCount(sheet);
  if (sheet.scan.status === "complete" && toFix) return toFix === 1 ? "One thing to look at" : `${toFix} things to look at`;
  return STATUS_COPY[sheet.scan.status] ?? "Waiting for the scan";
}
