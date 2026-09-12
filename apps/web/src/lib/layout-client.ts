import type { LayoutCheckResult, NodeMove, SceneGraph } from "@/types/contracts";

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  return (await response.json()) as T;
}

export function checkLayout(scanId: string, baseRevision: number, sequence: number, moves: NodeMove[]) {
  return postJson<LayoutCheckResult>(`/api/scans/${scanId}/layout-checks`, {
    base_revision: baseRevision,
    sequence,
    moves,
  });
}

export function saveLayout(scanId: string, baseRevision: number, moves: NodeMove[]) {
  return postJson<SceneGraph>(`/api/scans/${scanId}/revisions`, { base_revision: baseRevision, moves });
}
