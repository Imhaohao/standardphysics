import { CheckCircle, Question, WarningOctagon, MinusCircle } from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { STATUS_LABEL } from "@/lib/findings/format";
import type { FindingStatus } from "@/lib/findings/types";

const STATUS_STYLE: Record<FindingStatus, { icon: Icon; className: string }> = {
  fail: { icon: WarningOctagon, className: "text-problem" },
  needs_info: { icon: Question, className: "text-attention" },
  pass: { icon: CheckCircle, className: "text-pass" },
  not_applicable: { icon: MinusCircle, className: "text-ink-faint" },
};

export function statusTextClass(status: FindingStatus) {
  return STATUS_STYLE[status].className;
}

/** A finding's outcome as a coloured icon, with the words alongside unless `iconOnly`. */
export function StatusMark({ status, iconOnly = false, size = 18 }: { status: FindingStatus; iconOnly?: boolean; size?: number }) {
  const { icon: StatusIcon, className } = STATUS_STYLE[status];
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold ${className}`}>
      <StatusIcon size={size} weight="fill" aria-hidden={!iconOnly} aria-label={iconOnly ? STATUS_LABEL[status] : undefined} />
      {!iconOnly && STATUS_LABEL[status]}
    </span>
  );
}
