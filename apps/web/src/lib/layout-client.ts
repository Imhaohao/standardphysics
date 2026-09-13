import type { LayoutCheckResult, NodeMove, ProposalResult, SceneGraph } from "@/types/contracts";

export class ApiRefusal extends Error {
  constructor(readonly status: number, readonly error: string) {
    super(error);
  }
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ error: "" }));
    throw new ApiRefusal(response.status, String(detail.error ?? ""));
  }
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

export function proposeFix(scanId: string, baseRevision: number, findingIds: string[]) {
  return postJson<ProposalResult>(`/api/scans/${scanId}/proposals`, { base_revision: baseRevision, finding_ids: findingIds });
}
