import type { Proposal } from "@/types/contracts";

function plural(label: string, count: number): string {
  const lower = label.toLowerCase();
  if (count === 1) return `1 ${lower}`;
  return lower.endsWith("s") ? `${count} ${lower}es` : `${count} ${lower}s`;
}

/** "6 chairs -> 6 chairs", one line per kind of furniture. */
export function inventoryLines(proposal: Proposal): string[] {
  const labels = [...new Set([...Object.keys(proposal.inventory_before), ...Object.keys(proposal.inventory_after)])].sort();
  return labels.map((label) => {
    const before = proposal.inventory_before[label] ?? 0;
    const after = proposal.inventory_after[label] ?? 0;
    return `${plural(label, before)} -> ${plural(label, after)}`;
  });
}
