"use client";

import { useMemo, useState, type ReactNode } from "react";
import { saveAnswers } from "@/app/shops/actions";
import { InkedPlan } from "@/components/plan/InkedPlan";
import { MeasuredElements } from "@/components/report/MeasuredElements";
import { OwnerQuestions, type SaveAnswers } from "@/components/report/OwnerQuestions";
import { SHEET_GRID_CLASS, SheetField } from "@/components/sheet/SheetField";
import type { AnswerInput, Report } from "@/lib/api/types";
import { groupByElement, type ElementGroup } from "@/lib/findings/group";
import { findingPins, pinLabels } from "@/lib/findings/pins";
import { elementQuestions, questionCount } from "@/lib/findings/questions";
import { indexSubjects } from "@/lib/scene/describe";
import type { Scene } from "@/lib/scene/types";

const dateFormat = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

function countWhere(groups: ElementGroup[], status: ElementGroup["status"]) {
  return groups.filter((group) => group.status === status).length;
}

function useReportView(report: Report, scene: Scene | null) {
  return useMemo(() => {
    const groups = scene ? groupByElement(report.findings, indexSubjects(scene)) : [];
    const pins = findingPins(groups);
    return { groups, pins, labels: pinLabels(pins), elements: elementQuestions(groups) };
  }, [report, scene]);
}

interface ReportBodyProps {
  scanId: string;
  initialReport: Report;
  scene: Scene | null;
  /** A shared link shows the questions without a way to answer them. */
  readOnly?: boolean;
  children?: ReactNode;
}

/** The report under its header. Answering a question replaces the report with the one sp-server re-evaluated. */
export function ReportBody({ scanId, initialReport, scene, readOnly = false, children }: ReportBodyProps) {
  const [report, setReport] = useState(initialReport);
  const { groups, pins, labels, elements } = useReportView(report, scene);

  const save: SaveAnswers = async (answers: AnswerInput[]) => {
    const result = await saveAnswers(scanId, answers);
    if (result.report) setReport(result.report);
    return result.error;
  };

  return (
    <>
      <dl data-ink-avoid className={`${SHEET_GRID_CLASS} border border-ink *:bg-paper sm:grid-cols-4`}>
        <SheetField label="Checked">{dateFormat.format(new Date(report.created_at))}</SheetField>
        <SheetField label="Needs fixing">{countWhere(groups, "fail")}</SheetField>
        <SheetField label="Questions for you">{questionCount(elements)}</SheetField>
        <SheetField label="Meets every rule">{countWhere(groups, "pass")}</SheetField>
      </dl>
      <p className="max-w-3xl text-pretty text-ink-muted">
        We checked each element against the 2010 ADA Standards and California&rsquo;s Building Code, Chapter 11B. Where the two
        disagree, the stricter rule is the one your shop has to meet, and California&rsquo;s Unruh Act lets customers enforce it.
      </p>
      {scene && (
        <section aria-label="Floor plan with numbered findings" data-ink-avoid className="border border-ink bg-paper break-inside-avoid">
          <InkedPlan scene={scene} name="report" pins={pins} showNotes={false} className="drafting-grid h-[26rem] print:h-[22rem]" />
        </section>
      )}
      <OwnerQuestions elements={elements} labels={labels} onSave={readOnly ? undefined : save} />
      <MeasuredElements groups={groups} labels={labels} />
      {children}
    </>
  );
}
