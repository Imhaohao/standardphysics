"use client";

import { Camera, Question } from "@phosphor-icons/react";
import { useMemo, useState, useTransition, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { ChoiceGroup } from "@/components/ui/ChoiceGroup";
import { INPUT_CLASS } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import type { AnswerInput } from "@/lib/api/types";
import { citation } from "@/lib/findings/format";
import type { FindingPair } from "@/lib/findings/group";
import { answersToSave, choicesFor, unitWord, type ElementQuestions, type OpenCheck, type OwnerQuestion } from "@/lib/findings/questions";

/** Saves answers and resolves to an error to show, or null once the report has been replaced. */
export type SaveAnswers = (answers: AnswerInput[]) => Promise<string | null>;

type RenderAnswer = (question: OwnerQuestion) => ReactNode;

function citations(pair: FindingPair) {
  return [pair.ada, pair.cbc].flatMap((finding) => (finding ? [citation(finding)] : [])).filter(Boolean).join(" and ");
}

function CheckList({ checks }: { checks: FindingPair[] }) {
  return (
    <ul className="text-sm text-ink-muted">
      {checks.map((pair) => (
        <li key={pair.key}>
          {pair.governing.title}, {citations(pair)}
        </li>
      ))}
    </ul>
  );
}

function QuestionItem({ question, answer }: { question: OwnerQuestion; answer: ReactNode }) {
  return (
    <li>
      <fieldset className="flex flex-col gap-2.5">
        <legend className="mb-2.5 font-medium text-pretty">{question.ask.prompt}</legend>
        {answer}
        <CheckList checks={question.checks} />
      </fieldset>
    </li>
  );
}

function OpenCheckItem({ check }: { check: OpenCheck }) {
  return (
    <li className="flex flex-col gap-1">
      <span className="text-pretty">{check.ask}</span>
      <CheckList checks={check.checks} />
    </li>
  );
}

function QuestionList({ elements, labels, renderAnswer }: { elements: ElementQuestions[]; labels: Map<string, string>; renderAnswer?: RenderAnswer }) {
  return (
    <ol className="divide-y divide-ink/20">
      {elements.map(({ group, questions, openChecks }) => (
        <li key={group.subjectId} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 px-4 py-4">
          <span className="font-semibold tabular-nums text-ink-muted">{labels.get(group.subjectId) ?? ""}</span>
          <div className="flex flex-col gap-3">
            <span className="font-semibold">{group.name}</span>
            <ul className="flex flex-col gap-5">
              {questions.map((question) => (
                <QuestionItem key={question.key} question={question} answer={renderAnswer?.(question)} />
              ))}
              {openChecks.map((check) => (
                <OpenCheckItem key={check.ask} check={check} />
              ))}
            </ul>
          </div>
        </li>
      ))}
    </ol>
  );
}

interface AnswerControlProps {
  question: OwnerQuestion;
  value: string;
  error: string | undefined;
  disabled: boolean;
  onChange: (value: string) => void;
}

function NumberAnswer({ question, value, disabled, onChange }: AnswerControlProps) {
  const { ask } = question;
  return (
    <span className="flex max-w-64 items-center gap-2">
      <input
        type="text"
        inputMode={ask.value_type === "integer" ? "numeric" : "decimal"}
        aria-label={ask.unit ? `${ask.prompt} Answer in ${unitWord(ask.unit)}.` : ask.prompt}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={`${INPUT_CLASS} measurement`}
      />
      {ask.unit && <span className="shrink-0 text-ink-muted">{unitWord(ask.unit)}</span>}
    </span>
  );
}

function AnswerControl(props: AnswerControlProps) {
  const { question, value, error, disabled, onChange } = props;
  const numeric = question.ask.value_type === "number" || question.ask.value_type === "integer";
  return (
    <div className="flex flex-col gap-1.5 print:hidden">
      {numeric ? <NumberAnswer {...props} /> : <ChoiceGroup name={question.key} choices={choicesFor(question.ask)} value={value} onChange={onChange} disabled={disabled} />}
      {error && <span className="text-sm text-problem">{error}</span>}
    </div>
  );
}

type Result = { tone: "error" | "done"; text: string } | null;

function savedMessage(count: number) {
  return count === 1 ? "Saved your answer, and the report now counts it." : `Saved ${count} answers, and the report now counts them.`;
}

function useAnswerDrafts(elements: ElementQuestions[], onSave: SaveAnswers) {
  const questions = useMemo(() => elements.flatMap((entry) => entry.questions), [elements]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Result>(null);
  const [pending, startTransition] = useTransition();

  function submit(event: FormEvent) {
    event.preventDefault();
    const { answers, errors: invalid } = answersToSave(questions, drafts);
    setErrors(invalid);
    if (Object.keys(invalid).length > 0) return setResult({ tone: "error", text: "A few answers need another look. They're marked above." });
    startTransition(async () => {
      const error = await onSave(answers);
      setResult(error ? { tone: "error", text: error } : { tone: "done", text: savedMessage(answers.length) });
      if (!error) setDrafts({});
    });
  }

  const setDraft = (key: string, value: string) => setDrafts((current) => ({ ...current, [key]: value }));
  const filled = Object.values(drafts).some((draft) => draft.trim() !== "");
  return { drafts, errors, result, pending, filled, submit, setDraft };
}

function AnswerForm({ elements, labels, onSave }: { elements: ElementQuestions[]; labels: Map<string, string>; onSave: SaveAnswers }) {
  const { drafts, errors, result, pending, filled, submit, setDraft } = useAnswerDrafts(elements, onSave);
  const renderAnswer: RenderAnswer = (question) => (
    <AnswerControl question={question} value={drafts[question.key] ?? ""} error={errors[question.key]} disabled={pending} onChange={(value) => setDraft(question.key, value)} />
  );
  return (
    <form onSubmit={submit} noValidate>
      <QuestionList elements={elements} labels={labels} renderAnswer={renderAnswer} />
      <div className="sticky bottom-0 flex flex-wrap items-center gap-4 border-t border-ink bg-paper px-4 py-3 print:hidden">
        <Button type="submit" variant="primary" disabled={!filled || pending}>
          {pending ? "Saving your answers" : "Save answers"}
        </Button>
        {result && <Notice tone={result.tone}>{result.text}</Notice>}
      </div>
    </form>
  );
}

/** What we couldn't measure from the scan, asked plainly so the owner can answer from memory or a quick look. */
export function OwnerQuestions({ title, elements, labels, onSave }: { title: string; elements: ElementQuestions[]; labels: Map<string, string>; onSave?: SaveAnswers }) {
  if (elements.length === 0) return null;
  return (
    <section aria-labelledby="questions-heading" data-ink-avoid className="border border-ink bg-paper">
      <h2 id="questions-heading" className="heading-display flex items-center gap-2 border-b border-ink px-4 py-3 text-2xl">
        <Question size={24} weight="fill" aria-hidden className="text-attention" />
        {title}
      </h2>
      {elements.some((entry) => entry.questions.some((question) => question.ask.photo)) && (
        <p className="flex items-start gap-2 border-b border-ink/20 px-4 py-3 text-sm text-ink-muted text-pretty">
          <Camera size={18} aria-hidden className="mt-px shrink-0" />
          We&rsquo;d normally settle some of these from a photo. Your answer counts until we have one.
        </p>
      )}
      {onSave ? <AnswerForm elements={elements} labels={labels} onSave={onSave} /> : <QuestionList elements={elements} labels={labels} />}
    </section>
  );
}
