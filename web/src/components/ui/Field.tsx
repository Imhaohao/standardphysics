import type { ComponentProps, ReactNode } from "react";

/** A form field's input. The one place a thin neutral border sits on rounded corners. */
export const INPUT_CLASS = "w-full rounded-md border border-ink/30 bg-sheet px-3 py-2.5 text-base text-ink outline-none transition-colors focus:border-ink";

/** A labelled text input, with an optional hint under the label and an error under the input. */
export function TextField({ label, hint, error, className = "", ...input }: ComponentProps<"input"> & { label: string; hint?: ReactNode; error?: string | null }) {
  return (
    <label className={`flex flex-col gap-1.5 ${className}`}>
      <span className="text-sm font-medium">{label}</span>
      {hint && <span className="-mt-1 text-sm text-ink-muted text-pretty">{hint}</span>}
      <input aria-invalid={error ? true : undefined} className={INPUT_CLASS} {...input} />
      {error && <span className="text-sm text-problem">{error}</span>}
    </label>
  );
}
