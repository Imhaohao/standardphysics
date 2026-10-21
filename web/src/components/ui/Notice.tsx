import { CheckCircle, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

type Tone = "error" | "done";

const TONES: Record<Tone, { icon: typeof CheckCircle; className: string; role: "alert" | "status" }> = {
  error: { icon: WarningCircle, className: "text-problem", role: "alert" },
  done: { icon: CheckCircle, className: "text-pass", role: "status" },
};

/** A one-line result next to the control that caused it: what went wrong, or that it worked. */
export function Notice({ tone, children, className = "" }: { tone: Tone; children: ReactNode; className?: string }) {
  const { icon: ToneIcon, className: toneClass, role } = TONES[tone];
  return (
    <p role={role} className={`flex items-start gap-2 text-sm text-pretty ${toneClass} ${className}`}>
      <ToneIcon size={18} weight="fill" aria-hidden className="mt-px shrink-0" />
      <span className="text-ink">{children}</span>
    </p>
  );
}
