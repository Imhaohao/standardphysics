import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "quiet" | "chip";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-paper hover:bg-ink/85 px-5 py-3 text-base",
  quiet: "text-ink-muted hover:text-ink hover:bg-ink/5 px-3 py-2 text-sm",
  chip: "bg-sheet/95 text-ink shadow-[0_1px_2px_rgb(27_28_30/0.12),0_4px_16px_rgb(27_28_30/0.08)] hover:bg-sheet shrink-0 whitespace-nowrap px-3 py-2 text-sm aria-pressed:bg-ink aria-pressed:text-paper",
};

export function Button({
  variant = "quiet",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-2 rounded-lg font-medium transition-colors duration-150 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
