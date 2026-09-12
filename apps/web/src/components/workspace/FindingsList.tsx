"use client";

import { Camera, CaretDown, Check } from "@phosphor-icons/react";
import { useState, type KeyboardEvent } from "react";
import { formatInches, type FindingGroups } from "@/lib/findings";
import type { Finding } from "@/types/contracts";

type ListProps = { groups: FindingGroups; selectedId: string | null; onSelect: (finding: Finding) => void };

function OutcomeMark({ outcome }: { outcome: Finding["outcome"] }) {
  if (outcome === "problem") return <span className="mt-2 size-2.5 shrink-0 rounded-full bg-problem" aria-hidden />;
  if (outcome === "question") return <Camera size={18} className="mt-0.5 shrink-0 text-ink-muted" aria-hidden />;
  return <Check size={18} weight="bold" className="mt-0.5 shrink-0 text-pass" aria-hidden />;
}

function citationText(finding: Finding): string {
  return `${finding.citation.edition} ${finding.citation.section}`;
}

function FindingRow({ finding, selected, onSelect }: { finding: Finding; selected: boolean; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        data-finding-row
        aria-expanded={selected}
        onClick={onSelect}
        className={`flex w-full gap-3 rounded-lg px-3 py-3 text-left transition-colors ${
          selected ? "bg-sheet shadow-[0_1px_2px_rgb(27_28_30/0.1),0_8px_24px_rgb(27_28_30/0.07)]" : "hover:bg-ink/[0.04]"
        }`}
      >
        <OutcomeMark outcome={finding.outcome} />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="font-semibold leading-snug">{finding.title}</span>
            {finding.measured_inches !== null && (
              <span className="measurement shrink-0 text-ink-muted">{formatInches(finding.measured_inches)}</span>
            )}
          </span>
          {finding.detail && <span className="mt-1 block text-ink-muted">{finding.detail}</span>}
          {selected && finding.fix && (
            <span className="mt-3 block border-l-2 border-accent pl-3 font-medium text-ink">{finding.fix}</span>
          )}
          {selected && <span className="mt-2 block text-sm text-ink-faint">{citationText(finding)}</span>}
        </span>
      </button>
    </li>
  );
}

function moveFocus(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const rows = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("[data-finding-row]")];
  const index = rows.indexOf(document.activeElement as HTMLButtonElement);
  const next = rows[index + (event.key === "ArrowDown" ? 1 : -1)];
  if (!next) return;
  event.preventDefault();
  next.focus();
  next.click();
}

function Section({ heading, findings, ...props }: { heading: string; findings: Finding[] } & Omit<ListProps, "groups">) {
  if (findings.length === 0) return null;
  return (
    <section className="mt-6 first:mt-0">
      <h2 className="px-3 text-sm font-semibold text-ink-muted">{heading}</h2>
      <ul className="mt-2 flex flex-col gap-1">
        {findings.map((finding) => (
          <FindingRow
            key={finding.id}
            finding={finding}
            selected={finding.id === props.selectedId}
            onSelect={() => props.onSelect(finding)}
          />
        ))}
      </ul>
    </section>
  );
}

export function FindingsList({ groups, selectedId, onSelect }: ListProps) {
  const [showPasses, setShowPasses] = useState(false);
  const passSelected = groups.passes.some((finding) => finding.id === selectedId);
  const passesOpen = showPasses || passSelected;

  return (
    <nav aria-label="Findings" onKeyDown={moveFocus}>
      <Section heading="To fix" findings={groups.problems} selectedId={selectedId} onSelect={onSelect} />
      <Section heading="Send us a photo" findings={groups.questions} selectedId={selectedId} onSelect={onSelect} />
      {groups.passes.length > 0 && (
        <section className="mt-6">
          <button
            type="button"
            aria-expanded={passesOpen}
            onClick={() => setShowPasses(!passesOpen)}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-ink-muted hover:bg-ink/[0.04]"
          >
            <CaretDown size={14} weight="bold" className={`transition-transform ${passesOpen ? "" : "-rotate-90"}`} aria-hidden />
            {groups.passes.length} {groups.passes.length === 1 ? "check passes" : "checks pass"}
          </button>
          {passesOpen && <Section heading="" findings={groups.passes} selectedId={selectedId} onSelect={onSelect} />}
        </section>
      )}
    </nav>
  );
}
