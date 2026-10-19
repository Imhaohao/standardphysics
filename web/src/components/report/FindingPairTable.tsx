import { StatusMark } from "@/components/ui/StatusMark";
import { citation, formatMeasured, formatRequirement, jurisdictionName } from "@/lib/findings/format";
import type { FindingPair } from "@/lib/findings/group";
import type { Finding } from "@/lib/findings/types";

function CodeCell({ finding }: { finding: Finding | null }) {
  if (!finding) return <td className="px-3 py-3 align-top text-ink-faint">Not covered</td>;
  return (
    <td className="px-3 py-3 align-top">
      <span className="block font-semibold">{citation(finding) ?? jurisdictionName(finding.jurisdiction)}</span>
      <span className="measurement block">{formatRequirement(finding.required) ?? "Asks you"}</span>
      <span className="mt-1 block text-sm">
        <StatusMark status={finding.status} size={16} />
      </span>
    </td>
  );
}

function stricterNote(pair: FindingPair) {
  if (!pair.ada || !pair.cbc) return null;
  const [ada, cbc] = [formatRequirement(pair.ada.required), formatRequirement(pair.cbc.required)];
  if (ada === cbc && pair.ada.status === pair.cbc.status) return null;
  return pair.governing.jurisdiction === "CBC11B" ? "California is stricter here, so its rule is the one to meet." : "The ADA is stricter here, so its rule is the one to meet.";
}

/** Each requirement on its own row: what we measured, and what the ADA and California each ask for. */
export function FindingPairTable({ pairs }: { pairs: FindingPair[] }) {
  return (
    <table className="w-full table-fixed border-collapse text-left">
      <thead>
        <tr className="border-b border-ink text-sm text-ink-muted">
          <th scope="col" className="w-2/5 px-3 py-2 font-medium">What we checked</th>
          <th scope="col" className="w-1/6 px-3 py-2 font-medium">Measured</th>
          <th scope="col" className="px-3 py-2 font-medium">2010 ADA Standards</th>
          <th scope="col" className="px-3 py-2 font-medium">California 11B</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map((pair) => {
          const note = stricterNote(pair);
          return (
            <tr key={pair.key} className="border-b border-ink/20 break-inside-avoid">
              <td className="px-3 py-3 align-top text-pretty">
                {pair.governing.message}
                {note && <span className="mt-1 block text-sm text-ink-muted">{note}</span>}
              </td>
              <td className="measurement px-3 py-3 align-top text-lg">{formatMeasured(pair.governing.measured) ?? "Not measured"}</td>
              <CodeCell finding={pair.ada} />
              <CodeCell finding={pair.cbc} />
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
