import type { Report, Scan } from "@/lib/api/types";
import type { Finding } from "@/lib/findings/types";
import type { Scene } from "@/lib/scene/types";
import reportJson from "./sample-report.json";
import sceneJson from "./sample-scene.json";

/**
 * The bundled sample shop: Apple's RoomPlan "living room" sample (fixtures/roomplan) streamed through a real
 * sp-server by `pnpm fixture:capture`, so the scene is sp-core's conversion and the report is the engine's own.
 */
export const SAMPLE_SCAN_ID = "sample-living-room";
export const SAMPLE_SCENE = sceneJson as unknown as Scene;
export const SAMPLE_REPORT = reportJson as unknown as Report;
export const SAMPLE_FINDINGS: Finding[] = SAMPLE_REPORT.findings;

export const SAMPLE_SCANS: Scan[] = [
  { id: SAMPLE_SCAN_ID, name: "Front of house", site_name: "Corner shop", status: "complete", created_at: SAMPLE_REPORT.created_at, updated_at: SAMPLE_REPORT.created_at },
];
