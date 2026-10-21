"use client";

import { useMemo, useState, type ReactNode } from "react";
import { saveAnswers } from "@/app/shops/actions";
import { InkedPlan } from "@/components/plan/InkedPlan";
import { GivenAnswers } from "@/components/report/GivenAnswers";
import { MeasuredElements } from "@/components/report/MeasuredElements";
import { OwnerQuestions, type SaveAnswers } from "@/components/report/OwnerQuestions";
import { SHEET_GRID_CLASS, SheetField } from "@/components/sheet/SheetField";
import type { Answer, AnswerInput, Report } from "@/lib/api/types";
import { givenAnswers, type GivenAnswer } from "@/lib/findings/answers";
import { groupByElement, type ElementGroup } from "@/lib/findings/group";
import { findingPins, pinLabels } from "@/lib/findings/pins";
import { elementQuestions, questionCount } from "@/lib/findings/questions";
import { indexSubjects } from "@/lib/scene/describe";
import type { Scene } from "@/lib/scene/types";

const dateFormat = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

function countWhere(groups: ElementGroup[], status: ElementGroup["status"]) {
  return groups.filter((group) => group.status === status).length;
}

function useReportView(report: Report, answers: Answer[], scene: Scene | null) {
  const subjects = useMemo(() => (scene ? indexSubjects(scene) : null), [scene]);
  const view = useMemo(() => {
    const groups = subjects ? groupByElement(report.findings, subjects) : [];
    const pins = findingPins(groups);
    return { groups, pins, labels: pinLabels(pins), elements: elementQuestions(groups) };
  }, [report, subjects]);
  const given = useMemo(() => givenAnswers(answers, subjects ?? new Map()), [answers, subjects]);
  return { ...view, given };
}

interface ReportBodyProps {
  scanId: string;
  initialReport: Report;
  /** The answers already given. A shared link has none to show. */
  initialAnswers?: Answer[];
  scene: Scene | null;
  /** A shared link shows the questions without a way to answer them. */
  readOnly?: boolean;
  children?: ReactNode;
}

/** The report under its header. Answering a question replaces the report with the one sp-server re-evaluated. */
export function ReportBody({ scanId, initialReport, initialAnswers = [], scene, readOnly = false, children }: ReportBodyProps) {
  const [report, setReport] = useState(initialReport);
  const [answers, setAnswers] = useState(initialAnswers);
  const { groups, pins, labels, elements, given } = useReportView(report, answers, scene);

  const save: SaveAnswers = async (inputs: AnswerInput[]) => {
    const result = await saveAnswers(scanId, inputs);
    if (result.report) setReport(result.report);
    if (result.answers) setAnswers(result.answers);
    return result.error;
  };
  const questionsTitle = readOnly ? "Questions for the owner" : "Questions for you";
  const clear = ({ answer }: GivenAnswer) => save([{ subject_id: answer.subject_id, metric: answer.metric, value: null }]);

  return (
    <>
      <dl data-ink-avoid className={`${SHEET_GRID_CLASS} border border-ink *:bg-paper sm:grid-cols-4`}>
        <SheetField label="Checked">{dateFormat.format(new Date(report.created_at))}</SheetField>
        <SheetField label="Needs fixing">{countWhere(groups, "fail")}</SheetField>
        <SheetField label={questionsTitle}>{questionCount(elements)}</SheetField>
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
      <OwnerQuestions title={questionsTitle} elements={elements} labels={labels} onSave={readOnly ? undefined : save} />
      {!readOnly && <GivenAnswers rows={given} onClear={clear} />}
      <MeasuredElements groups={groups} labels={labels} questionsTitle={questionsTitle} />
      {children}
    </>
  );
}
