import type { ScanChanges } from "@/lib/api/types";

const MAX_NAME_LENGTH = 200;

export type ScanNameResult = { changes: ScanChanges; error: null } | { changes: null; error: string };

/** The PATCH body for a rename. The scan needs a name; an empty shop name clears it, so the scan's name shows instead. */
export function scanChangesFrom(name: string, siteName: string): ScanNameResult {
  const [scan, site] = [name.trim(), siteName.trim()];
  if (!scan) return { changes: null, error: "Give the scan a name, like Front of house." };
  if (scan.length > MAX_NAME_LENGTH || site.length > MAX_NAME_LENGTH) return { changes: null, error: `Keep names under ${MAX_NAME_LENGTH} characters.` };
  return { changes: { name: scan, site_name: site || null }, error: null };
}
