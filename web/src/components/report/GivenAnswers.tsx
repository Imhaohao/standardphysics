"use client";

import { Camera, CaretDown } from "@phosphor-icons/react";
import { useState, useTransition } from "react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import type { GivenAnswer } from "@/lib/findings/answers";

type ClearAnswer = (row: GivenAnswer) => Promise<string | null>;

function AnswerRow({ row, onClear }: { row: GivenAnswer; onClear: ClearAnswer }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  return (
    <li className="grid gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-center">
      <span className="min-w-0">
        <span className="block font-semibold">{row.element}</span>
        <span className="block text-sm text-ink-muted">{row.topic}</span>
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="font-semibold">{row.value}</span>
        {row.fromPhoto && (
          <span className="flex items-center gap-1.5 text-sm text-ink-muted">
            <Camera size={16} aria-hidden />
            Read from your photo
          </span>
        )}
      </span>
      <Button onClick={() => startTransition(async () => setError(await onClear(row)))} disabled={pending} aria-label={`Clear your answer about ${row.topic.toLowerCase()} for ${row.element}`} className="-ms-3 w-fit sm:ms-0 print:hidden">
        {pending ? "Clearing" : "Clear answer"}
      </Button>
      {error && <Notice tone="error" className="sm:col-span-3">{error}</Notice>}
    </li>
  );
}

/** Answers already given, folded away so they don't crowd the open questions. Clearing one asks its question again. */
export function GivenAnswers({ rows, onClear }: { rows: GivenAnswer[]; onClear: ClearAnswer }) {
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="answers-heading" data-ink-avoid className="border border-ink bg-paper print:hidden">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 hover:bg-ink/5 [&::-webkit-details-marker]:hidden">
          <h2 id="answers-heading" className="heading-display text-2xl">
            Your answers
          </h2>
          <span className="flex items-center gap-2 text-ink-muted">
            <span className="tabular-nums">{rows.length}</span>
            <CaretDown size={18} weight="bold" aria-hidden className="transition-transform duration-150 group-open:rotate-180" />
          </span>
        </summary>
        <ul className="divide-y divide-ink/20 border-t border-ink">
          {rows.map((row) => (
            <AnswerRow key={row.key} row={row} onClear={onClear} />
          ))}
        </ul>
      </details>
    </section>
  );
}
